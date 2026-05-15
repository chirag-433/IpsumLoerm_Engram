import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from adapter import Adapter
from schema import Context, Event, IncidentSignal
from typing import Iterable, Literal
from engine.ingest import AnvilIngester
from engine.memory import MemoryStore
from engine.graph import CausalGraphBuilder
from engine.reconstruct import reconstruct_context as _reconstruct


class Engine(Adapter):
    def __init__(self):   # NO arguments — harness calls Engine() with no args
        self.ingester = AnvilIngester()
        self.memory = MemoryStore(self.ingester)
        self.graph = CausalGraphBuilder(self.ingester)
        self._all_events = []

    def ingest(self, events: Iterable[Event]) -> None:
        event_list = list(events)
        self.ingester.consume(event_list)
        self._all_events.extend(event_list)

        for e in event_list:
            kind = e.get("kind")

            if kind == "incident_signal":
                incident_id = e.get("incident_id", "")
                service = e.get("service", "") or ""
                canonical_svc = self.ingester.canonical(service)
                ts = e.get("ts", "")

                nearby = [
                    ev for ev in self._all_events
                    if _ts_diff_minutes(ev.get("ts", ""), ts) <= 30
                ]
                fp = self.memory.fingerprint(canonical_svc, nearby)
                family_id = incident_id.rsplit("-", 1)[-1] if "-" in incident_id else incident_id

                self.memory.store_family(
                    family_id, fp, canonical_svc,
                    "|".join([ev.get("kind", "") for ev in nearby]),
                    ts
                )
                self.memory.store_incident(incident_id, family_id, canonical_svc, ts, fp)

            elif kind == "remediation":
                incident_id = e.get("incident_id", "")
                try:
                    rows = self.ingester.conn.execute(
                        "SELECT family_id FROM incidents WHERE incident_id = ?",
                        [incident_id]
                    ).fetchall()
                    family_id = rows[0][0] if rows else incident_id.rsplit("-", 1)[-1]
                except Exception:
                    family_id = incident_id.rsplit("-", 1)[-1]

                self.memory.store_remediation(
                    incident_id, family_id,
                    e.get("action", "rollback"),
                    e.get("target", ""),
                    e.get("version", ""),
                    e.get("outcome", ""),
                    e.get("ts", "")
                )

    def reconstruct_context(
        self,
        signal: IncidentSignal,
        mode: Literal["fast", "deep"] = "fast",
    ) -> Context:
        return _reconstruct(signal, self.ingester, self.memory, self.graph, mode)

    def close(self):
        self.ingester.close()


def _ts_diff_minutes(ts1: str, ts2: str) -> float:
    try:
        from datetime import datetime
        def parse(ts):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return abs((parse(ts1) - parse(ts2)).total_seconds() / 60)
    except Exception:
        return 9999.0
