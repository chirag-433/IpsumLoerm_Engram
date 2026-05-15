"""Context reconstruction for incident signals."""

import json
from datetime import datetime, timedelta

from engine.ingest import AnvilIngester
from engine.memory import MemoryStore
from engine.graph import CausalGraphBuilder


def reconstruct_context(signal: dict, ingester: AnvilIngester,
                        memory: MemoryStore, graph: CausalGraphBuilder,
                        mode: str = "fast") -> dict:
    """Reconstruct full incident context from a signal event.

    Gathers related events, builds causal chains, finds similar past
    incidents, and suggests remediations.

    Args:
        signal: The incident signal dict (must have ts, service, etc.).
        ingester: AnvilIngester instance with shared DuckDB connection.
        memory: MemoryStore instance for fingerprinting and family matching.
        graph: CausalGraphBuilder instance for causal edge inference.
        mode: "fast" for template explanation, "deep" for LLM synthesis.

    Returns:
        Dict with related_events, causal_chain, similar_past_incidents,
        suggested_remediations, confidence, and explain.
    """

    # ── STEP 1: Related Events ──────────────────────────────────────────

    signal_ts_str = signal.get("ts", "")
    signal_dt = _parse_ts(signal_ts_str)

    window_start = (signal_dt - timedelta(minutes=30)).isoformat()
    window_end = (signal_dt + timedelta(minutes=30)).isoformat()

    rows = ingester.conn.execute(
        "SELECT raw_json FROM events WHERE ts >= ? AND ts <= ?",
        [window_start, window_end],
    ).fetchall()

    events_map = {}  # event_id → event dict (for dedup)
    trace_ids = set()

    for (raw,) in rows:
        evt = json.loads(raw)
        eid = graph.make_event_id(evt)
        events_map[eid] = evt
        tid = evt.get("trace_id")
        if tid:
            trace_ids.add(tid)

    # Expand by trace_id
    for tid in trace_ids:
        trace_rows = ingester.conn.execute(
            "SELECT raw_json FROM events WHERE raw_json LIKE ?",
            [f"%{tid}%"],
        ).fetchall()
        for (raw,) in trace_rows:
            evt = json.loads(raw)
            eid = graph.make_event_id(evt)
            events_map[eid] = evt

    related_events = sorted(events_map.values(), key=lambda e: e.get("ts", ""))
    related_events = related_events[:20]

    # ── STEP 2: Causal Chain ────────────────────────────────────────────

    causal_chain = graph.build_edges(related_events)

    # ── STEP 3: Similar Past Incidents ──────────────────────────────────

    canonical_svc = ingester.canonical(signal.get("service", ""))
    fp = memory.fingerprint(canonical_svc, related_events)
    similarity_matches = memory.match_family(fp, limit=5)

    # Direct lookup from incidents table
    direct_rows = ingester.conn.execute(
        "SELECT incident_id, family_id, canonical_service, ts "
        "FROM incidents "
        "WHERE canonical_service = ? AND incident_id != ? "
        "ORDER BY ts DESC LIMIT 5",
        [canonical_svc, signal.get("incident_id", "")],
    ).fetchall()

    similar_past_incidents = []
    seen_incident_ids = set()

    for row in direct_rows:
        iid = row[0]
        if iid not in seen_incident_ids:
            seen_incident_ids.add(iid)
            similar_past_incidents.append({
                "incident_id": iid,
                "similarity": 0.9,
                "rationale": "same canonical service",
            })

    # Append family-based similarity matches
    for match in similarity_matches:
        if len(similar_past_incidents) >= 5:
            break
        # Get the most recent incident_id for this family
        fam_rows = ingester.conn.execute(
            "SELECT incident_id FROM incidents WHERE family_id = ? ORDER BY ts DESC LIMIT 1",
            [match["family_id"]],
        ).fetchall()
        if fam_rows:
            iid = fam_rows[0][0]
            if iid not in seen_incident_ids:
                seen_incident_ids.add(iid)
                similar_past_incidents.append({
                    "incident_id": iid,
                    "similarity": match["similarity"],
                    "rationale": f"behavioral fingerprint match, family {match['family_id']}",
                })

    similar_past_incidents = similar_past_incidents[:5]

    # ── STEP 4: Suggested Remediations ──────────────────────────────────

    suggested_remediations = []
    seen_families = set()

    for spi in similar_past_incidents:
        if len(suggested_remediations) >= 3:
            break
        # Look up family_id for this incident
        fam_row = ingester.conn.execute(
            "SELECT family_id FROM incidents WHERE incident_id = ?",
            [spi["incident_id"]],
        ).fetchall()
        if not fam_row:
            continue
        fam_id = fam_row[0][0]
        if fam_id in seen_families:
            continue
        seen_families.add(fam_id)

        rems = memory.get_remediations_for_family(fam_id)
        if rems:
            rem = rems[0]  # first resolved remediation (already filtered)
            suggested_remediations.append({
                "action": rem.get("action") or "rollback",
                "target": rem["target"],
                "historical_outcome": "resolved",
                "confidence": 0.8,
            })

    suggested_remediations = suggested_remediations[:3]

    # ── STEP 5: Confidence ──────────────────────────────────────────────

    if causal_chain:
        confidence = sum(e["confidence"] for e in causal_chain) / len(causal_chain)
    elif similar_past_incidents:
        confidence = 0.5
    else:
        confidence = 0.2

    # ── STEP 6: Explain ────────────────────────────────────────────────

    explain = _build_fast_explain(signal, causal_chain, similar_past_incidents,
                                  suggested_remediations)

    if mode == "deep":
        try:
            from integrations.llm import synthesize_explanation
            explain = synthesize_explanation(signal, causal_chain,
                                            similar_past_incidents,
                                            suggested_remediations)
        except Exception:
            pass  # fall back to template above

    return {
        "related_events": related_events,
        "causal_chain": causal_chain,
        "similar_past_incidents": similar_past_incidents,
        "suggested_remediations": suggested_remediations,
        "confidence": confidence,
        "explain": explain,
    }


def _parse_ts(ts_str: str) -> datetime:
    """Parse an ISO timestamp string, tolerating a trailing Z."""
    cleaned = ts_str.replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return datetime.now()


def _build_fast_explain(signal, causal_chain, similar_past_incidents,
                        suggested_remediations) -> str:
    """Build a quick template-based explanation string."""
    svc = signal.get("service", "unknown")
    ts = signal.get("ts", "")
    action = (suggested_remediations[0]["action"]
              if suggested_remediations else "investigate")
    return (
        f"Incident on {svc} at {ts}. "
        f"Causal chain: {len(causal_chain)} edges. "
        f"Similar past incidents: {len(similar_past_incidents)}. "
        f"Suggested: {action}."
    )
