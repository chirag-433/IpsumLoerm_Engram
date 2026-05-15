import pytest

from engine import CanonicalRegistry, _extract_family, _tokenize_trigger, PersistentContextEngine
from engine.memory import MemoryStore
from engine.graph import CausalGraphBuilder
from engine.ingest import AnvilIngester

def test_canonical_registry():
    reg = CanonicalRegistry()
    # ensure returns name
    assert reg.ensure("svc-A") == "svc-A"
    
    # apply_rename resolves alias
    reg.apply_rename("svc-A", "svc-B")
    assert reg.canonical("svc-B") == "svc-A"
    
    # cycle detection doesn't hang
    reg.apply_rename("svc-B", "svc-A")
    assert reg.canonical("svc-A") == "svc-A"

def test_extract_family():
    assert _extract_family("inc-007") == 7
    assert _extract_family("bad-string") is None

def test_tokenize_trigger():
    tokens = _tokenize_trigger("Alert: CPU > 90%!")
    assert isinstance(tokens, set)
    assert "" not in tokens
    assert "cpu" in tokens

def test_persistent_context_engine_ingest():
    engine = PersistentContextEngine()
    events = [
        {"kind": "topology", "ts": "2023-01-01T00:00:00Z", "change": "rename", "from_": "svc-A", "to": "svc-B"},
        {"kind": "incident_signal", "ts": "2024-01-01T00:00:00Z", "service": "svc-B", "incident_id": "inc-1"}
    ]
    engine.ingest(events)
    # Check if canonical matches
    assert "svc-A" in engine._incidents_by_canonical
    assert len(engine._incidents_by_canonical["svc-A"]) == 1

def test_persistent_context_engine_reconstruct():
    engine = PersistentContextEngine()
    events = [
        {"kind": "deploy", "ts": "2024-01-01T00:00:00Z", "service": "svc-A"},
        {"kind": "metric", "ts": "2024-01-01T00:10:00Z", "service": "svc-A", "name": "latency", "value": 3000},
        {"kind": "log", "ts": "2024-01-01T00:20:00Z", "service": "svc-A", "level": "error"},
        {"kind": "incident_signal", "ts": "2024-01-01T00:30:00Z", "service": "svc-A", "incident_id": "inc-1"}
    ]
    engine.ingest(events)
    signal = {"kind": "incident_signal", "ts": "2024-01-01T00:30:00Z", "service": "svc-A", "incident_id": "inc-2"}
    ctx = engine.reconstruct_context(signal)
    
    assert len(ctx["causal_chain"]) > 0
    assert ctx["similar_past_incidents"] is not None
    assert len(ctx["suggested_remediations"]) > 0
    assert ctx["suggested_remediations"][0]["action"] == "rollback"

def test_memorystore_jaccard():
    ingester = AnvilIngester()
    mem = MemoryStore(ingester)
    assert mem.jaccard_similarity("abc", "abc") == 1.0
    assert mem.jaccard_similarity("", "") == 1.0
    assert mem.jaccard_similarity("abc", "xyz") == 0.0
    
def test_causalgraphbuilder_edges():
    ingester = AnvilIngester()
    gb = CausalGraphBuilder(ingester)
    events = [
        {"kind": "deploy", "ts": "2024-01-01T00:00:00Z", "service": "svc-A"},
        {"kind": "metric", "ts": "2024-01-01T00:15:00Z", "service": "svc-A", "name": "latency"}
    ]
    edges = gb.build_edges(events)
    assert len(edges) == 1
    assert edges[0]["confidence"] == 0.8
