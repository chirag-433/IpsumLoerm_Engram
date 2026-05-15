"""FastAPI backend for Engram — Persistent Context Engine."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from engine.ingest import AnvilIngester
from engine.memory import MemoryStore
from engine.graph import CausalGraphBuilder
from engine.reconstruct import reconstruct_context

_ingester: AnvilIngester | None = None
_memory: MemoryStore | None = None
_graph: CausalGraphBuilder | None = None
_all_events: list[dict] = []
_ws_clients: set[WebSocket] = set()


# ── Lifecycle ───────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize engine components on startup, close on shutdown."""
    global _ingester, _memory, _graph
    _ingester = AnvilIngester(os.getenv("DUCKDB_PATH", ":memory:"))
    _memory = MemoryStore(_ingester)
    _graph = CausalGraphBuilder(_ingester)
    yield
    if _ingester:
        _ingester.close()


app = FastAPI(title="Engram — Persistent Context Engine", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ─────────────────────────────────────────────────────────────

def _ts_diff_minutes(ts1: str, ts2: str) -> float:
    """Return absolute time difference in minutes between two ISO timestamps."""
    try:
        def parse(ts):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return abs((parse(ts1) - parse(ts2)).total_seconds() / 60)
    except Exception:
        return 9999.0


def _process_event(event: dict) -> None:
    """Handle incident_signal and remediation events for storage.

    Mirrors the processing logic from the benchmark adapter so that
    ingested events automatically populate families, incidents, and
    remediations in the shared DuckDB store.
    """
    kind = event.get("kind")

    if kind == "incident_signal":
        incident_id = event.get("incident_id", "")
        service = event.get("service", "") or ""
        canonical_svc = _ingester.canonical(service)
        ts = event.get("ts", "")

        nearby = [
            ev for ev in _all_events
            if _ts_diff_minutes(ev.get("ts", ""), ts) <= 30
        ]
        fp = _memory.fingerprint(canonical_svc, nearby)
        family_id = incident_id.rsplit("-", 1)[-1] if "-" in incident_id else incident_id

        _memory.store_family(
            family_id, fp, canonical_svc,
            "|".join([ev.get("kind", "") for ev in nearby]),
            ts,
        )
        _memory.store_incident(incident_id, family_id, canonical_svc, ts, fp)

    elif kind == "remediation":
        incident_id = event.get("incident_id", "")
        try:
            rows = _ingester.conn.execute(
                "SELECT family_id FROM incidents WHERE incident_id = ?",
                [incident_id],
            ).fetchall()
            family_id = rows[0][0] if rows else incident_id.rsplit("-", 1)[-1]
        except Exception:
            family_id = incident_id.rsplit("-", 1)[-1]

        _memory.store_remediation(
            incident_id, family_id,
            event.get("action", "rollback"),
            event.get("target", ""),
            event.get("version", ""),
            event.get("outcome", ""),
            event.get("ts", ""),
        )


# ── Routes ──────────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_events(events: list[dict]):
    """Ingest a batch of events into the engine."""
    _ingester.consume(events)
    _all_events.extend(events)

    for e in events:
        _process_event(e)

    _ingester._flush()

    return {"status": "ok", "count": len(events)}


@app.post("/reconstruct")
async def reconstruct(signal: dict):
    """Reconstruct full incident context from a signal and broadcast via WebSocket."""
    ctx = reconstruct_context(signal, _ingester, _memory, _graph, mode="fast")

    # Broadcast to all connected WebSocket clients
    for ws in list(_ws_clients):
        try:
            await ws.send_json(ctx)
        except Exception:
            _ws_clients.discard(ws)

    return ctx


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "engine": "engram"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """WebSocket endpoint for real-time context updates."""
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
