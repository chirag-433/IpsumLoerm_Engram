"""Anvil event ingestion engine backed by DuckDB."""

import json

import duckdb


class AnvilIngester:
    """Ingests events into a DuckDB-backed store with service alias resolution."""

    def __init__(self, db_path: str = ":memory:"):
        self.conn = duckdb.connect(db_path)
        self.alias_map: dict[str, str] = {}  # new_name → old_name
        self._buffer: list[dict] = []
        self._create_tables()

    def _create_tables(self):
        """Create the events table if it doesn't already exist."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id       TEXT,
                ts       TEXT,
                kind     TEXT,
                service  TEXT,
                raw_json TEXT
            )
            """
        )

    def canonical(self, service_name: str) -> str:
        """Resolve a service name through the alias chain to its canonical name.

        Uses iterative lookup with cycle protection via a visited set.

        Examples:
            alias_map = {"billing-svc": "payments-svc"}
            canonical("billing-svc") -> "payments-svc"

            alias_map = {"C": "B", "B": "A"}
            canonical("C") -> "A"
        """
        visited: set[str] = set()
        current = service_name

        while current in self.alias_map:
            if current in visited:
                break  # cycle detected — stop
            visited.add(current)
            current = self.alias_map[current]

        return current

    def consume(self, events: list) -> None:
        """Consume a list of event dicts, tracking renames and buffering for flush."""
        for event in events:
            if event.get("kind") == "topology" and event.get("change") == "rename":
                self.alias_map[event["to"]] = event["from_"]

            self._buffer.append(event)

            if len(self._buffer) >= 100:
                self._flush()

    def _flush(self):
        """Batch-insert the buffer into the events table and clear it."""
        try:
            if not self._buffer:
                return

            rows = []
            for e in self._buffer:
                row_id = f"{e.get('ts', '')}_{e.get('kind', '')}_{e.get('service', '')}"
                service = e.get("service") or e.get("target") or ""
                raw_json = json.dumps(e)
                rows.append((row_id, e.get("ts", ""), e.get("kind", ""), service, raw_json))

            self.conn.executemany(
                "INSERT INTO events (id, ts, kind, service, raw_json) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self._buffer.clear()
        except Exception:
            pass

    def close(self):
        """Flush remaining events and close the database connection."""
        self._flush()
        self.conn.close()
