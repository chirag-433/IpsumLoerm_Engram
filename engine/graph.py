"""Causal graph builder for deriving cause-effect edges from events."""

from datetime import datetime

from engine.ingest import AnvilIngester


class CausalGraphBuilder:
    """Builds causal edges between events using temporal and service-based rules."""

    def __init__(self, ingester: AnvilIngester):
        self.ingester = ingester

    def make_event_id(self, event: dict) -> str:
        """Generate a deterministic ID for an event."""
        return f"{event.get('ts', '')}_{event.get('kind', '')}_{event.get('service', '')}"

    def build_edges(self, events: list) -> list:
        """Apply causal rules to a list of events and return deduped edges.

        Rules applied:
            1. deploy → latency spike (within 30 min, same canonical service)
            2. latency spike → error log (within 10 min, same trace or service)
            3. error log → incident signal (within 5 min, same canonical service)

        Args:
            events: List of event dicts with ts, kind, service, etc.

        Returns:
            List of edge dicts with cause_event_id, effect_event_id,
            evidence, and confidence.
        """

        def time_diff_minutes(ts1: str, ts2: str) -> float:
            """Return the absolute time difference in minutes between two ISO timestamps."""
            try:
                fmt_candidates = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                                  "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%fZ",
                                  "%Y-%m-%dT%H:%M"]
                dt1 = None
                dt2 = None
                for fmt in fmt_candidates:
                    if dt1 is None:
                        try:
                            dt1 = datetime.strptime(ts1.replace("Z", ""), fmt.replace("Z", ""))
                        except ValueError:
                            pass
                    if dt2 is None:
                        try:
                            dt2 = datetime.strptime(ts2.replace("Z", ""), fmt.replace("Z", ""))
                        except ValueError:
                            pass
                if dt1 is None or dt2 is None:
                    return 9999.0
                return abs((dt2 - dt1).total_seconds()) / 60.0
            except Exception:
                return 9999.0

        sorted_events = sorted(events, key=lambda e: e.get("ts", ""))

        edges = []
        seen = set()  # (cause_id, effect_id) for deduplication

        for i, a in enumerate(sorted_events):
            a_kind = a.get("kind", "")
            a_svc = self.ingester.canonical(a.get("service") or a.get("target") or "")
            a_id = self.make_event_id(a)
            a_ts = a.get("ts", "")

            for j in range(i + 1, len(sorted_events)):
                b = sorted_events[j]
                b_kind = b.get("kind", "")
                b_svc = self.ingester.canonical(b.get("service") or b.get("target") or "")
                b_id = self.make_event_id(b)
                b_ts = b.get("ts", "")

                diff = time_diff_minutes(a_ts, b_ts)

                # Rule 1: deploy → latency spike
                if (a_kind == "deploy"
                        and b_kind == "metric"
                        and "latency" in (b.get("name") or "").lower()
                        and a_svc == b_svc
                        and 0 < diff <= 30):
                    key = (a_id, b_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "cause_event_id": a_id,
                            "effect_event_id": b_id,
                            "evidence": "deploy preceded latency spike",
                            "confidence": 0.8,
                        })

                # Rule 2: latency spike → error log
                if (a_kind == "metric"
                        and "latency" in (a.get("name") or "").lower()
                        and b_kind == "log"
                        and b.get("level") == "error"
                        and (
                            (a.get("trace_id") and a.get("trace_id") == b.get("trace_id"))
                            or a_svc == b_svc
                        )
                        and 0 < diff <= 10):
                    key = (a_id, b_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "cause_event_id": a_id,
                            "effect_event_id": b_id,
                            "evidence": "latency spike preceded error logs",
                            "confidence": 0.7,
                        })

                # Rule 3: error log → incident signal
                if (a_kind == "log"
                        and a.get("level") == "error"
                        and b_kind == "incident_signal"
                        and a_svc == b_svc
                        and 0 < diff <= 5):
                    key = (a_id, b_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "cause_event_id": a_id,
                            "effect_event_id": b_id,
                            "evidence": "errors triggered incident signal",
                            "confidence": 0.9,
                        })

        return edges
