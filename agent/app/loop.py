"""The agent loop: a hand-written tool-use loop over the Anthropic Messages API.

This is a while loop, not a fixed sequence. Each turn we ask the model what to do
next; it emits a tool call; we run the tool; we feed the result back; it decides its
next move from what it saw. The investigation path is not hardcoded.

The loop is a generator: it ``yield``s decision-log events (SSE frames) as they
happen, so the browser can watch the agent in real time. FastAPI iterates this sync
generator in a threadpool, so the blocking Anthropic + sandbox calls don't stall the
server. The stream of events is the decision log — there is no separate logging pass.

Mechanics to note:
  * The handshake: append the assistant turn (which contains the `tool_use` block)
    to `messages` before the matching `tool_result`. The API rejects a tool_result
    that doesn't follow its tool_use.
  * Choosing the next move lives in the next `messages.create` call, not in our code.
    Our code only executes whatever tool the model asked for.
  * Self-correction: a sandbox error comes back as a `tool_result` with
    `is_error=True`; the model reads the traceback next turn and rewrites.
  * Termination: the model calls `finish`. The loop cap is a separate safety net,
    not the thing that decides "done".
"""
from __future__ import annotations

import os
from typing import Any, Iterator, Optional

from . import config, grounding, profile, prompts, tools
from .events import SSEEmitter
from .sandbox import run_pandas


def run_investigation(
    question: str,
    df_path: str,
    emitter: SSEEmitter,
    client: Optional[Any] = None,
) -> Iterator[str]:
    """Investigate ``question`` over the dataset at ``df_path``; yield SSE frames."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    # The conversation. The system prompt sets the posture; the first user turn is
    # the task. Everything after this is built by the loop, turn by turn.
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                "The dataset is already loaded as a pandas DataFrame named `df`.\n\n"
                f"Question to investigate: {question}"
            ),
        }
    ]

    step = 0
    tokens_used = 0
    consecutive_errors = 0  # self-correction: how many times in a row a snippet failed
    results_by_step: dict[int, str] = {}  # the grounding ledger: step -> result summary

    yield emitter.run_start(question, config.MODEL)

    while True:
        # -- Hard guards. Checked before every model call so the agent can neither
        #    spiral nor overspend. These are safety nets, not control flow: they
        #    never pick a tool or a phase.
        if step >= config.MAX_STEPS:
            yield emitter.cap_hit(step, "max_steps")
            yield from _forced_finish(client, messages, results_by_step, emitter, step, "max_steps")
            return
        if tokens_used >= config.TOKEN_BUDGET:
            yield emitter.cap_hit(step, "token_budget")
            yield from _forced_finish(client, messages, results_by_step, emitter, step, "token_budget")
            return

        # -- Force profile_data on step 0 so the model sees the schema before it
        #    hypothesizes. After step 0 the model chooses its own tool every turn.
        #    Forcing a specific tool is incompatible with extended thinking, so step 0
        #    runs with thinking off (profiling needs no reasoning anyway).
        first_step = step == 0
        yield emitter.step_start(step, "orient" if first_step else "query")

        resp = _model_call(
            client,
            messages,
            tool_choice=(
                {"type": "tool", "name": "profile_data"}
                if first_step
                else {"type": "auto", "disable_parallel_tool_use": True}
            ),
            thinking_on=not first_step,
        )
        tokens_used += _tokens(resp)

        # Emit the model's reasoning + why it stopped this turn.
        yield emitter.decision(step, _thinking_text(resp) or _assistant_text(resp), resp.stop_reason)

        # -- Termination A: the model called finish(). Ground the report, emit it, stop.
        finish_block = _first_tool(resp, "finish")
        if finish_block is not None:
            report = grounding.ground_check(finish_block.input, results_by_step)
            yield emitter.report(step, report["answer"], report["findings"])
            yield emitter.done(step, "finish")
            return

        # -- Termination B: the model produced plain text and no tool. Nudge it once
        #    to act or finish, then continue the loop.
        if resp.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": resp.content})
            messages.append(
                {
                    "role": "user",
                    "content": "Continue with a tool call, or call finish if the question is answered and grounded.",
                }
            )
            step += 1
            continue

        # -- Act. Append the assistant turn first (the tool_use), then run each tool
        #    and collect its result. Order matters: a tool_result must follow its
        #    tool_use in the transcript.
        messages.append({"role": "assistant", "content": resp.content})
        tool_results: list[dict] = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "profile_data":
                snippet = profile.profile_snippet()
                yield emitter.hypothesis(step, "Look at the data before hypothesizing.")
                yield emitter.code(step, snippet)
                run = run_pandas(snippet, df_path)
                content = run.stdout or run.result_repr or run.error or run.traceback or ""
                results_by_step[step] = _summarize(content)
                yield emitter.result(step, "profile", content)
                tool_results.append(_tool_result(block.id, _labeled(step, content), is_error=not run.ok))
            elif block.name == "run_pandas":
                # Self-correction lives inside this helper. `yield from` streams its
                # events and hands back the updated consecutive-error count.
                consecutive_errors = yield from _run_pandas_tool(
                    block, df_path, step, consecutive_errors, results_by_step, tool_results, emitter
                )
            # (finish is handled above; there is no other tool)

        # Feed all tool results back as the next user turn. On the next iteration the
        # model reads them, interprets, and decides the next move.
        messages.append({"role": "user", "content": tool_results})
        step += 1


def _run_pandas_tool(block, df_path, step, consecutive_errors, results_by_step, tool_results, emitter):
    """Run one run_pandas call: emit its events, append its tool_result, and return
    the updated ``consecutive_errors`` count. A generator — ``yield from`` it and
    capture the return value.

    An error is handed back to the model verbatim as ``is_error=True`` so it can
    self-correct, but a lead that keeps failing is abandoned after a per-step cap so
    a hopeless snippet can't loop forever.
    """
    inp = block.input or {}
    code = inp.get("code", "")
    chart = inp.get("chart")

    yield emitter.hypothesis(step, inp.get("hypothesis", ""))
    yield emitter.code(step, code, attempt=consecutive_errors)

    run = run_pandas(code, df_path, chart=chart)

    if run.ok:
        content = run.result_repr or run.stdout or ""
        results_by_step[step] = _summarize(content)
        yield emitter.result(step, "pandas", content)
        # The model chose whether/how to chart; we just render what it asked.
        if run.chart_png and isinstance(chart, dict):
            yield emitter.chart(step, chart.get("kind", ""), chart.get("reason", ""), run.chart_png)
        tool_results.append(_tool_result(block.id, _labeled(step, content), is_error=False))
        return 0  # success resets the error streak

    # -- error path ----------------------------------------------------------------
    consecutive_errors += 1
    traceback_text = run.traceback or run.error or "unknown error"
    yield emitter.error(step, traceback_text, attempt=consecutive_errors - 1)

    if consecutive_errors >= config.MAX_RETRIES_PER_STEP:
        # Abandon this lead — but still hand the traceback back so the model can pivot.
        yield emitter.retry_exhausted(step)
        tool_results.append(
            _tool_result(
                block.id,
                _labeled(
                    step,
                    traceback_text
                    + "\n\n[This approach has failed repeatedly. Abandon it and try a different angle, or finish if you can already answer.]",
                ),
                is_error=True,
            )
        )
        return 0

    # Feed the traceback straight back. Next turn the model reads it and rewrites.
    yield emitter.retry(step, consecutive_errors)
    tool_results.append(_tool_result(block.id, _labeled(step, traceback_text), is_error=True))
    return consecutive_errors


def _forced_finish(client, messages, results_by_step, emitter, step, reason):
    """Loop-cap safety net: ask the model to write a grounded report from only what
    it already has. Not an open-ended continuation — this fires when a guard trips,
    not when the agent decides it's done.
    """
    messages.append(
        {
            "role": "user",
            "content": "You have reached your investigation budget. Call finish now with a grounded report using only the results you already have.",
        }
    )
    resp = _model_call(client, messages, tool_choice={"type": "tool", "name": "finish"}, thinking_on=False)
    fb = _first_tool(resp, "finish")
    if fb is not None:
        report = grounding.ground_check(fb.input, results_by_step)
        yield emitter.report(step, report["answer"], report["findings"])
    else:
        yield emitter.report(
            step,
            _assistant_text(resp) or "Stopped at the investigation budget before reaching a firm conclusion.",
            [],
        )
    yield emitter.done(step, reason)


# --- small helpers over the Anthropic response ---------------------------------


def _model_call(client, messages, *, tool_choice, thinking_on):
    """One Messages API call with the agent's tools. Adaptive thinking is enabled
    except when we force a specific tool (thinking is incompatible with a forced
    tool_choice)."""
    _apply_prompt_cache(messages)  # cache the growing conversation prefix (~0.1x on re-reads)
    kwargs = dict(
        model=config.MODEL,
        max_tokens=config.MAX_OUTPUT_TOKENS,
        system=prompts.SYSTEM_PROMPT,
        messages=messages,
        tools=tools.TOOLS,
        tool_choice=tool_choice,
    )
    if thinking_on:
        kwargs["thinking"] = {"type": "adaptive"}
    resp = client.messages.create(**kwargs)
    if os.getenv("DEBUG_USAGE") and getattr(resp, "usage", None):
        u = resp.usage
        print(
            f"[usage] input={u.input_tokens} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)} "
            f"cache_write={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"output={u.output_tokens}",
            flush=True,
        )
    return resp


def _apply_prompt_cache(messages) -> None:
    """Keep exactly one prompt-cache breakpoint, on the last block of the last
    message, so the whole growing prefix (tools + system + every prior turn) is
    written once and re-read at ~0.1x on each subsequent turn.

    Each loop turn appends more history, so the breakpoint moves forward; we clear
    the old one first to stay within the 4-breakpoint limit. We only mark
    list-content turns (our tool_result turns) — a plain-string user turn is skipped
    (and there's no meaningful prefix to cache that early anyway).
    """
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    last = messages[-1].get("content")
    if isinstance(last, list) and last and isinstance(last[-1], dict):
        last[-1]["cache_control"] = {"type": "ephemeral"}


def _tokens(resp) -> int:
    u = getattr(resp, "usage", None)
    if not u:
        return 0
    return (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0)


def _first_tool(resp, name):
    for b in resp.content:
        if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == name:
            return b
    return None


def _thinking_text(resp) -> str:
    parts = [getattr(b, "thinking", "") for b in resp.content if getattr(b, "type", None) == "thinking"]
    return "\n".join(p for p in parts if p).strip()


def _assistant_text(resp) -> str:
    parts = [getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n".join(p for p in parts if p).strip()


def _tool_result(tool_use_id, content, *, is_error) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": str(content), "is_error": is_error}


def _labeled(step: int, content: str) -> str:
    # Prefix each tool result with its step number so the model can cite it as
    # `evidence_step` in finish() — it cannot see our internal step indices otherwise.
    return f"[step {step}]\n{content}"


def _summarize(text: str, limit: int = 800) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + " …"
