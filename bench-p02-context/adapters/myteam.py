import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from adapter import Adapter
from schema import Context, Event, IncidentSignal
from typing import Iterable, Literal
from engine import PersistentContextEngine


class Engine(Adapter):
    def __init__(self) -> None:
        self._engine = PersistentContextEngine()

    def ingest(self, events: Iterable[Event]) -> None:
        self._engine.ingest(events)

    def reconstruct_context(
        self, signal: IncidentSignal, mode: Literal["fast", "deep"] = "fast"
    ) -> Context:
        return self._engine.reconstruct_context(signal, mode=mode)

    def close(self) -> None:
        self._engine.close()
