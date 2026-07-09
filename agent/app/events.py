"""The SSE event contract. Defines the decision-log events that the agent loop
emits and the viewer renders.

``web/lib/investigator/events.ts`` mirrors this file. If you change an event
here, change it there.

Every event shares an envelope::

    {"type": ..., "run_id": ..., "seq": <monotonic int>, "step": <int>, "ts": <float>}

``SSEEmitter`` stamps that envelope, assigns the monotonic ``seq`` (so the client
can order/dedupe), and serializes to the SSE wire format ``data: <json>\\n\\n``.
The loop calls ``emitter.<event>(...)`` and yields the returned frame straight
into the ``StreamingResponse``.
"""
from __future__ import annotations

import json
import time
from typing import Any

# --- Event type constants (keep in sync with events.ts) -----------------------
RUN_START = "run_start"
STEP_START = "step_start"
HYPOTHESIS = "hypothesis"
CODE = "code"
RESULT = "result"
ERROR = "error"
RETRY = "retry"
RETRY_EXHAUSTED = "retry_exhausted"
DECISION = "decision"
CHART = "chart"
CAP_HIT = "cap_hit"
REPORT = "report"
DONE = "done"
HEARTBEAT = "heartbeat"


class SSEEmitter:
    """Formats decision-log events as Server-Sent-Events frames.

    One emitter per investigation run. It owns the monotonic ``seq`` counter and
    the ``run_id`` so callers only pass the fields that vary per event.
    """

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._seq = 0

    def _frame(self, type_: str, step: int, **fields: Any) -> str:
        self._seq += 1
        payload = {
            "type": type_,
            "run_id": self.run_id,
            "seq": self._seq,
            "step": step,
            "ts": time.time(),
            **fields,
        }
        return f"data: {json.dumps(payload)}\n\n"

    # -- one method per event type (fields beyond the envelope) ---------------
    def run_start(self, question: str, model: str) -> str:
        return self._frame(RUN_START, -1, question=question, model=model)

    def step_start(self, step: int, phase: str) -> str:  # phase: "orient" | "query"
        return self._frame(STEP_START, step, phase=phase)

    def hypothesis(self, step: int, text: str) -> str:
        return self._frame(HYPOTHESIS, step, text=text)

    def code(self, step: int, code: str, attempt: int = 0) -> str:
        return self._frame(CODE, step, code=code, attempt=attempt)

    def result(self, step: int, kind: str, result: str, attempt: int = 0) -> str:
        # kind: "profile" | "pandas"
        return self._frame(RESULT, step, kind=kind, result=result, attempt=attempt)

    def error(self, step: int, traceback: str, attempt: int = 0) -> str:
        return self._frame(ERROR, step, traceback=traceback, attempt=attempt)

    def retry(self, step: int, attempt: int) -> str:
        return self._frame(RETRY, step, attempt=attempt)

    def retry_exhausted(self, step: int) -> str:
        return self._frame(RETRY_EXHAUSTED, step)

    def decision(self, step: int, thinking: str, stop_reason: str) -> str:
        return self._frame(DECISION, step, thinking=thinking, stop_reason=stop_reason)

    def chart(self, step: int, kind: str, reason: str, png: str) -> str:
        return self._frame(CHART, step, kind=kind, reason=reason, png=png)

    def cap_hit(self, step: int, reason: str) -> str:  # reason: "max_steps" | "token_budget"
        return self._frame(CAP_HIT, step, reason=reason)

    def report(self, step: int, answer: str, findings: list[dict[str, Any]]) -> str:
        # findings: [{"claim": str, "evidence_step": int}]
        return self._frame(REPORT, step, answer=answer, findings=findings)

    def done(self, step: int, stopped_reason: str) -> str:
        # stopped_reason: "finish" | "max_steps" | "token_budget"
        return self._frame(DONE, step, stopped_reason=stopped_reason)

    def heartbeat(self) -> str:
        return self._frame(HEARTBEAT, -1)
