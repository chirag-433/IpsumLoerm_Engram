"""
Adapter shim for the Persistent Context Engine.
Drop this into adapters/myteam.py in the bench-p02-context directory.
"""
from __future__ import annotations

import sys
import os

# Allow importing engine from parent directory if needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapter import Adapter
from schema import Context, Event, IncidentSignal
from engine import PersistentContextEngine


class Engine(Adapter):
    def __init__(self) -> None:
        self._engine = PersistentContextEngine()

    def ingest(self, events) -> None:
        self._engine.ingest(events)

    def reconstruct_context(self, signal: IncidentSignal, mode="fast") -> Context:
        return self._engine.reconstruct_context(signal, mode=mode)

    def close(self) -> None:
        self._engine.close()
