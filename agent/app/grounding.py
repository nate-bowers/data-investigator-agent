"""Grounding — enforce "no result, no claim" in CODE, not just the prompt (Block 6).

``results_by_step`` is the ledger of every result the model actually saw. Before we
emit the final report we walk each finding's ``evidence_step`` against that ledger:
a claim pointing at a step that produced no real result is flagged ungrounded, so
the trace can render it as such (a broken evidence link renders as broken — which is
exactly what proves the check is real). The prompt asks for grounding; this makes it
true.
"""
from __future__ import annotations

from typing import Any


def ground_check(finish_input: dict[str, Any], results_by_step: dict[int, Any]) -> dict[str, Any]:
    """Return the report with each finding tagged grounded / not, against the ledger."""
    answer = finish_input.get("answer", "")
    checked = []
    for f in finish_input.get("findings", []) or []:
        ev = f.get("evidence_step")
        try:
            ev_int: int | None = int(ev)
        except (TypeError, ValueError):
            ev_int = None
        grounded = ev_int is not None and ev_int in results_by_step
        checked.append(
            {"claim": f.get("claim", ""), "evidence_step": ev, "grounded": bool(grounded)}
        )
    return {"answer": answer, "findings": checked}
