from typing import Any, Dict, List, Literal, Optional, TypedDict

class Event(TypedDict, total=False):
    ts: str
    kind: str
    service: str
    target: str
    from_: str
    to: str
    change: str
    incident_id: str
    trigger: str
    trace_id: str
    name: str
    value: float
    level: str
    action: str
    outcome: str

class IncidentSignal(TypedDict, total=False):
    ts: str
    kind: str
    incident_id: str
    service: str
    trigger: str

class Context(TypedDict, total=False):
    related_events: List[Event]
    causal_chain: List[Dict[str, Any]]
    similar_past_incidents: List[Dict[str, Any]]
    suggested_remediations: List[Dict[str, Any]]
    confidence: float
    explain: str
