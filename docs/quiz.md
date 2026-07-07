# Whiteboard quiz

The real completion bar for this project isn't "it runs" — it's **you can whiteboard
the loop, termination, and self-correction from memory.** Answer these cold (no
peeking at the code), then check yourself against the answer key. If any answer is
shaky, re-read `how-the-loop-works.md` and the relevant part of `loop.py`.

Do these after you've read `loop.py` line by line.

## Questions

1. **Draw the loop.** Where exactly does the model decide what to compute next —
   point to the specific call.
2. Name one concrete difference between this and a hardcoded
   `profile → query → answer` pipeline.
3. A `run_pandas` call raises a `KeyError`. Trace what happens, step by step, until
   the model retries.
4. Why do we append the assistant's `content` to `messages` *before* the tool
   results — what breaks if we don't?
5. What stops an infinite loop, and what's the difference between the **loop cap**
   and the **retry cap**?
6. How does the agent decide it's *done* — and how would you prove to a skeptic that
   it wasn't just a step counter?
7. Why is the chart choice a *field on `run_pandas`* instead of a separate
   `choose_chart` tool? Name one thing that design gives up.
8. What does "grounding" mean here, and where is it enforced — in the prompt or in
   the code?

---

## Answer key (don't look until you've tried)

1. In the next `messages.create(...)` call (`_model_call` in `loop.py`). The model
   reads the last `tool_result` in `messages` and emits the next `tool_use`. Our
   code never chooses the next hypothesis.
2. Any of: the sequence of tools isn't fixed (the model picks each one); the path
   branches on what a result actually said; it can pivot or abandon a lead; it
   decides when to stop. In a pipeline all of that is hardcoded.
3. Sandbox runs the snippet → it throws → `SandboxResult.ok == False` with the full
   traceback → `_run_pandas_tool` emits an `error` event, increments
   `consecutive_errors`, emits `retry`, and appends a `tool_result` with
   `is_error=True` and the traceback as content → the loop feeds that back as the
   next user turn → next `messages.create`, the model reads the traceback and emits
   a corrected `run_pandas`.
4. The API requires every `tool_result` to follow the assistant `tool_use` it
   answers (matched by `tool_use_id`). Append the result without first appending the
   assistant turn and the request is rejected / the transcript desyncs.
5. The **loop cap** (`MAX_STEPS` / `TOKEN_BUDGET`, checked before each model call)
   bounds the whole investigation so it can't spiral or overspend. The **retry cap**
   (`MAX_RETRIES_PER_STEP`) bounds how many times *one* broken snippet is retried
   before we abandon that lead — it's per-step, so a single hopeless query can't
   consume the global budget.
6. The model calls `finish`. There is no `if step == N: answer` — deleting the caps
   doesn't remove the ability to finish. Proof for a skeptic: the caps are a
   *separate, visible* `cap_hit` event; a real self-stop has `finish → report →
   done` with no `cap_hit`. The trace distinguishes them.
7. It welds the chart to the exact `result` that motivated it (no re-derivation),
   keeps the tool surface at three tools (easier to whiteboard), and *omitting* the
   field is itself the "no chart" decision — still a per-step model choice, not a
   rule. What you give up: you can't chart a *stale* earlier result without
   recomputing it (fine, since grounding wants a fresh result per claim anyway).
8. "No result, no claim": every finding in `finish` must reference a step that
   actually produced a result. It's enforced in **code** — `grounding.ground_check`
   walks each finding's `evidence_step` against the `results_by_step` ledger and
   flags any that don't match — not just requested in the prompt.
