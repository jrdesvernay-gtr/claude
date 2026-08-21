"""Registry of Item 20 table-format handlers.

A handler is a pure function: str (Item 20 section text) -> list[ItemRow].
No file I/O, no network — this is the sandboxed interface Agent 1 (handler
drafter) must also honor when it drafts a new handler at runtime.

New handlers (deterministic or agent-drafted) register here. Agent-drafted
handlers go live immediately but start with probation_runs_remaining > 0 and
HANDLER_PROBATION_CONFIDENCE until they've run HANDLER_PROBATION_RUNS times
cleanly (i.e. passed the Table 1 cross-check each time).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pipeline.config import (
    HANDLER_PROBATION_RUNS,
    HANDLER_PROBATION_CONFIDENCE,
    HANDLER_PROVEN_CONFIDENCE,
)
from pipeline.models import ItemRow

HandlerFn = Callable[[str], list[ItemRow]]


@dataclass
class Handler:
    id: str
    state: str
    description: str
    fn: HandlerFn
    source: str = "deterministic"          # 'deterministic' | 'agent_drafted'
    probation_runs_remaining: int = 0
    confidence_score: float = HANDLER_PROVEN_CONFIDENCE
    matches: Callable[[dict], bool] = field(default=lambda fingerprint: False)


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, handler: Handler) -> None:
        self._handlers[handler.id] = handler

    def register_agent_drafted(self, handler_id: str, state: str, description: str, fn: HandlerFn) -> Handler:
        h = Handler(
            id=handler_id,
            state=state,
            description=description,
            fn=fn,
            source="agent_drafted",
            probation_runs_remaining=HANDLER_PROBATION_RUNS,
            confidence_score=HANDLER_PROBATION_CONFIDENCE,
        )
        self.register(h)
        return h

    def get(self, handler_id: str) -> Handler | None:
        return self._handlers.get(handler_id)

    def find_match(self, state: str, fingerprint: dict) -> Handler | None:
        for handler in self._handlers.values():
            if handler.state == state and handler.matches(fingerprint):
                return handler
        return None

    def record_clean_run(self, handler_id: str) -> None:
        """Call after a run that passed the Table 1 cross-check. Advances a
        probationary handler toward proven confidence; no-op for handlers
        already off probation.
        """
        h = self._handlers.get(handler_id)
        if h is None or h.probation_runs_remaining <= 0:
            return
        h.probation_runs_remaining -= 1
        if h.probation_runs_remaining == 0:
            h.confidence_score = HANDLER_PROVEN_CONFIDENCE
        else:
            # ramp linearly from probation floor to proven ceiling
            done = HANDLER_PROBATION_RUNS - h.probation_runs_remaining
            span = HANDLER_PROVEN_CONFIDENCE - HANDLER_PROBATION_CONFIDENCE
            h.confidence_score = round(HANDLER_PROBATION_CONFIDENCE + span * done / HANDLER_PROBATION_RUNS, 2)


registry = HandlerRegistry()
