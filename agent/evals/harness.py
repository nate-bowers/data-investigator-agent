"""Run one eval case through the real agent loop, then grade it three ways.

Runner: drives ``loop.run_investigation`` with a real Anthropic client and parses the
SSE frames it yields back into event dicts.

Graders:
  accuracy       exact-match for numeric/categorical answers, LLM judge for causal ones.
  grounding      every number in the final report must trace to a value the agent
                 actually computed (the "ledger" = all result events).
  selfcorrect    of the run_pandas calls that raised, how many were followed by a
                 passing query before the 3-retry cap (a recovery).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app import config, loop
from app.events import SSEEmitter


# --------------------------------------------------------------------------- run

@dataclass
class RunResult:
    case_id: str
    events: list[dict] = field(default_factory=list)
    answer: str = ""
    findings: list[dict] = field(default_factory=list)
    ledger_text: str = ""       # all computed result text the model saw
    done_reason: str = ""
    error: Optional[str] = None  # set if the run failed terminally


def _parse_frame(frame: str) -> Optional[dict]:
    frame = frame.strip()
    if not frame.startswith("data:"):
        return None
    try:
        return json.loads(frame[len("data:"):].strip())
    except Exception:
        return None


def run_case(case, client=None) -> RunResult:
    """Run the agent on one case and collect its decision-log events."""
    emitter = SSEEmitter("eval_" + case.id)
    res = RunResult(case_id=case.id)
    ledger_parts: list[str] = []
    try:
        for frame in loop.run_investigation(case.question, case.dataset_path, emitter, client=client):
            ev = _parse_frame(frame)
            if ev is None:
                continue
            res.events.append(ev)
            t = ev.get("type")
            if t == "result":
                ledger_parts.append(str(ev.get("result", "")))
            elif t == "report":
                res.answer = ev.get("answer", "")
                res.findings = ev.get("findings", []) or []
            elif t == "done":
                res.done_reason = ev.get("stopped_reason", "")
            elif t == "error" and ev.get("step") == -1:
                res.error = ev.get("traceback", "terminal error")
    except Exception as e:  # a crash in the loop itself
        res.error = f"{type(e).__name__}: {e}"
    res.ledger_text = "\n".join(ledger_parts)
    return res


# ------------------------------------------------------------------- number utils

_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}
# a number (with optional commas / decimal) then an optional %/word multiplier
_NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|thousand|million|billion|\bk\b|\bbn\b)?", re.I)


def _numbers(text: str, *, skip_small_ints: bool = False) -> list[float]:
    out: list[float] = []
    for m in _NUM_RE.finditer(text or ""):
        raw, suf = m.group(1), (m.group(2) or "").lower()
        if raw.count(",") and re.search(r",\d{1,2}(?!\d)", raw):
            pass  # keep as-is; European decimals are not expected here
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        if suf and suf != "%":
            val *= _MULT.get(suf, 1)
        if skip_small_ints and val == int(val) and abs(val) < 10:
            continue
        out.append(val)
    return out


def _close(a: float, b: float, tol: float, rel: bool) -> bool:
    if rel:
        return abs(a - b) <= tol * max(abs(b), 1e-9)
    return abs(a - b) <= tol


# ----------------------------------------------------------------------- graders

JUDGE_MODEL = config.MODEL
_GRADE_TOOL = {
    "name": "grade",
    "description": "Record whether the agent's answer matches the reference conclusion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "correct": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["correct", "reason"],
    },
}


def grade_accuracy(case, run: RunResult, judge_client=None) -> dict:
    """Return {correct, method, detail}."""
    ans = (run.answer or "") + " " + " ".join(f.get("claim", "") for f in run.findings)
    if run.error or not run.answer:
        return {"correct": False, "method": "no-report", "detail": run.error or "no report produced"}

    if case.kind == "categorical":
        ok = case.reference.lower() in ans.lower()
        return {"correct": ok, "method": "exact", "detail": f"looked for {case.reference!r}"}

    if case.kind == "numeric":
        ref = float(case.reference)
        cands = _numbers(ans)
        ok = any(_close(c, ref, case.tol or 0.0, case.rel) for c in cands)
        return {"correct": ok, "method": "exact",
                "detail": f"ref={ref} tol={'{:.1%}'.format(case.tol) if case.rel else case.tol} found={cands[:8]}"}

    # causal -> LLM judge
    if judge_client is None:
        import anthropic

        judge_client = anthropic.Anthropic(timeout=60.0, max_retries=2)
    prompt = (
        f"Question: {case.question}\n\n"
        f"Reference answer (ground truth): {case.reference}\n\n"
        f"Agent's answer: {run.answer}\n\n"
        "Does the agent's answer reach the same main conclusion as the reference? Ignore wording, "
        "extra detail, and exact numbers; judge the core causal conclusion. Call grade()."
    )
    resp = judge_client.messages.create(
        model=JUDGE_MODEL, max_tokens=400,
        system="You are a strict but fair grader of data-analysis conclusions.",
        messages=[{"role": "user", "content": prompt}],
        tools=[_GRADE_TOOL], tool_choice={"type": "tool", "name": "grade"},
    )
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use" and b.name == "grade":
            return {"correct": bool(b.input.get("correct")), "method": "judge",
                    "detail": b.input.get("reason", "")}
    return {"correct": False, "method": "judge", "detail": "judge returned no verdict"}


def grade_grounding(run: RunResult) -> dict:
    """Every number in the report must match a number the agent computed."""
    if run.error or not run.answer:
        return {"report_numbers": 0, "grounded": 0, "ungrounded": [], "n_a": True}
    report_text = (run.answer or "") + " " + " ".join(f.get("claim", "") for f in run.findings)
    report_nums = _numbers(report_text, skip_small_ints=True)
    ledger_nums = _numbers(run.ledger_text)
    ungrounded = []
    for n in report_nums:
        if not any(_close(n, l, 0.01, True) or _close(n, l, 0.5, False) for l in ledger_nums):
            ungrounded.append(n)
    # evidence_step integrity: each finding cites a step that produced a result
    result_steps = {e.get("step") for e in run.events if e.get("type") == "result"}
    bad_steps = [f.get("evidence_step") for f in run.findings
                 if f.get("evidence_step") not in result_steps]
    return {
        "report_numbers": len(report_nums),
        "grounded": len(report_nums) - len(ungrounded),
        "ungrounded": ungrounded,
        "bad_evidence_steps": bad_steps,
        "n_a": False,
    }


def grade_selfcorrect(run: RunResult) -> dict:
    """Recovery rate = errored run_pandas calls that were followed by a passing query
    before the 3-retry cap."""
    total = recovered = exhausted = 0
    chain = 0
    for e in run.events:
        t = e.get("type")
        if t == "error" and e.get("step", -1) >= 0:
            chain += 1
            total += 1
        elif t == "result" and e.get("kind") == "pandas":
            if chain:
                recovered += chain
                chain = 0
        elif t == "retry_exhausted":
            exhausted += chain
            chain = 0
    return {"errors": total, "recovered": recovered, "exhausted": exhausted + chain,
            "recovery_rate": (recovered / total) if total else None}
