"""Memory store for incident families, incidents, and remediations."""

import hashlib

from engine.ingest import AnvilIngester


class MemoryStore:
    """Stores and matches incident patterns using a shared DuckDB connection."""

    def __init__(self, ingester: AnvilIngester):
        self.ingester = ingester
        self.conn = ingester.conn  # share same DuckDB connection
        self._create_tables()

    def _create_tables(self):
        """Create incident_families, incidents, and remediations tables."""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_families (
                family_id         TEXT PRIMARY KEY,
                fingerprint       TEXT,
                canonical_service TEXT,
                event_sequence    TEXT,
                occurrence_count  INT DEFAULT 1,
                last_seen         TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id       TEXT PRIMARY KEY,
                family_id         TEXT,
                canonical_service TEXT,
                ts                TEXT,
                fingerprint       TEXT
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS remediations (
                incident_id TEXT PRIMARY KEY,
                family_id   TEXT,
                action      TEXT,
                target      TEXT,
                version     TEXT,
                outcome     TEXT,
                ts          TEXT
            )
            """
        )

    def fingerprint(self, canonical_service: str, events_near_incident: list) -> str:
        """Generate a SHA-256 fingerprint from sorted event signatures.

        Args:
            canonical_service: The resolved service name (for context).
            events_near_incident: List of event dicts near the incident window.

        Returns:
            A hex-digest string representing the incident pattern.
        """
        sorted_events = sorted(events_near_incident, key=lambda e: e.get("ts", ""))

        signatures = []
        for e in sorted_events:
            svc = self.ingester.canonical(
                e.get("service") or e.get("target") or ""
            )
            signatures.append(f"{svc}:{e.get('kind', '')}")

        joined = "|".join(signatures)
        return hashlib.sha256(joined.encode()).hexdigest()

    @staticmethod
    def jaccard_similarity(fp1: str, fp2: str) -> float:
        """Compute Jaccard similarity using character bigrams.

        Args:
            fp1: First fingerprint string.
            fp2: Second fingerprint string.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        def bigrams(s):
            return set(s[i:i + 2] for i in range(len(s) - 1))

        b1 = bigrams(fp1)
        b2 = bigrams(fp2)

        if not b1 and not b2:
            return 1.0
        if not b1 or not b2:
            return 0.0

        return len(b1 & b2) / len(b1 | b2)

    def store_incident(self, incident_id: str, family_id: str,
                       canonical_service: str, ts: str, fingerprint: str):
        """Insert an incident record (ignored if duplicate ID)."""
        self.conn.execute(
            "INSERT INTO incidents VALUES (?, ?, ?, ?, ?) ON CONFLICT (incident_id) DO NOTHING",
            [incident_id, family_id, canonical_service, ts, fingerprint],
        )

    def store_family(self, family_id: str, fingerprint: str,
                     canonical_service: str, event_sequence: str, ts: str):
        """Insert or replace an incident family record."""
        self.conn.execute(
            "INSERT INTO incident_families "
            "(family_id, fingerprint, canonical_service, event_sequence, occurrence_count, last_seen) "
            "VALUES (?, ?, ?, ?, 1, ?) "
            "ON CONFLICT (family_id) DO UPDATE SET "
            "fingerprint=excluded.fingerprint, canonical_service=excluded.canonical_service, "
            "event_sequence=excluded.event_sequence, last_seen=excluded.last_seen",
            [family_id, fingerprint, canonical_service, event_sequence, ts],
        )

    def store_remediation(self, incident_id: str, family_id: str, action: str,
                          target: str, version: str, outcome: str, ts: str):
        """Insert or replace a remediation record."""
        self.conn.execute(
            "INSERT INTO remediations VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (incident_id) DO UPDATE SET "
            "action=excluded.action, outcome=excluded.outcome, ts=excluded.ts",
            [incident_id, family_id, action, target, version, outcome, ts],
        )

    def match_family(self, fingerprint: str, limit: int = 5) -> list:
        """Find the most similar incident families by Jaccard bigram similarity.

        Args:
            fingerprint: The fingerprint to match against.
            limit: Maximum number of results to return.

        Returns:
            List of dicts sorted by similarity descending.
        """
        rows = self.conn.execute(
            "SELECT family_id, fingerprint, canonical_service FROM incident_families"
        ).fetchall()

        scored = []
        for row in rows:
            sim = self.jaccard_similarity(fingerprint, row[1])
            scored.append({
                "family_id": row[0],
                "similarity": sim,
                "canonical_service": row[2],
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:limit]

    def get_remediations_for_family(self, family_id: str) -> list:
        """Get all successful remediations for a given incident family.

        Args:
            family_id: The incident family to look up.

        Returns:
            List of remediation dicts ordered by timestamp descending.
        """
        rows = self.conn.execute(
            "SELECT * FROM remediations WHERE family_id = ? AND outcome = 'resolved' "
            "ORDER BY ts DESC",
            [family_id],
        ).fetchall()

        columns = ["incident_id", "family_id", "action", "target",
                    "version", "outcome", "ts"]
        return [dict(zip(columns, row)) for row in rows]
