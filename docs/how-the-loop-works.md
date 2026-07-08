# How the loop works

This is the doc to read until you can whiteboard the agent from memory. Everything
here maps to `agent/app/loop.py` — keep it open alongside this.

---

## 1. Agent vs. workflow (in one sentence)

**A workflow hardcodes the path; an agent decides the path at runtime.** In a
workflow *your code* says "profile, then query, then answer." In an agent, *the
model* decides each next step from the last result, and your code just runs
whatever tool it asked for.

This project is worthless if it's secretly a workflow — the entire value is that
the path is chosen by the model, live, based on what the data said. So the loop is
written to make that literally true: **delete every `if step ==` line in `loop.py`
and it still investigates.** (Those lines are only a first-step nudge and a safety
cap — never "what to do next.")

## 2. It's a WHILE, not a sequence

The core is one loop (`run_investigation`):

```
ask the model what to do  →  it emits a tool call  →  run the tool
      ↑                                                     │
      └───────────  feed the result back  ←─────────────────┘
```

Each turn, the result of the last tool call is added to the conversation, and the
*next* `messages.create` call is the model looking at that result and choosing what
to compute next. The loop just keeps turning until the model calls `finish`.

Why a loop and not a sequence: because we don't know the path in advance. "Signups
dropped in March" might branch to *channel* → *campaign*, or to *geography*, or hit
a dead end and pivot. The branch point is the model reading a result — which only
exists inside a loop.

## 3. The tool-use handshake (the part people get wrong)

One round of the loop, in API terms:

1. We call `messages.create(..., tools=TOOLS)`.
2. The model responds with `stop_reason == "tool_use"` and a `tool_use` block:
   `{type: "tool_use", id: "toolu_…", name: "run_pandas", input: {…}}`.
3. We **append the assistant turn** (the whole `resp.content`, including that
   `tool_use` block) to `messages`.
4. We run the tool and append a **`tool_result`** as a *user* turn:
   `{type: "tool_result", tool_use_id: "toolu_…", content: "<result>", is_error: false}`.
5. Back to step 1 — now the model sees the result.

**Order matters:** the `tool_result` must come *after* the assistant turn that
holds its `tool_use`, and it references that call by `tool_use_id`. If you append
the result without first appending the assistant turn, the API rejects it. In
`loop.py` that's the `messages.append({"role":"assistant", ...})` line that comes
*before* we build `tool_results`.

## 4. Where "decide next move" actually lives

Not in our code. Our loop has **no branch that chooses a hypothesis or a phase.**
The only place the next move is decided is the next `messages.create` call — the
model reads the last `tool_result` and emits the next `tool_use`. Our code is a
dumb executor: "the model asked for `run_pandas` with this code → run it → hand
back the result." That's the whole point, and it's what makes this an agent.

## 5. Forcing the first look (`profile_data`)

The one thing we *do* force: on step 0 we set
`tool_choice={"type":"tool","name":"profile_data"}` so the agent must look at the
data before it hypothesizes — it can't hallucinate a column it never saw. We force
it to **look**, never to **answer**. After step 0, `tool_choice` is `"auto"` and
the model is on its own.

(Aside: forcing a specific tool is incompatible with extended thinking, so step 0
runs with thinking off — profiling needs no reasoning. Steps 1+ turn adaptive
thinking on.)

## 6. Self-correction (`is_error` → the model rewrites)

When the sandbox runs LLM-written pandas that throws, we don't hide it. We hand the
**verbatim traceback back as a `tool_result` with `is_error: true`**. Next turn the
model sees the real error and rewrites its code. That's the whole mechanism — an
error is just another result the model reasons about.

The cap: `_run_pandas_tool` counts consecutive failures. Under
`MAX_RETRIES_PER_STEP` (~3) we keep handing tracebacks back so it can fix itself;
at the cap we tell it to abandon that lead (so a hopeless snippet can't loop
forever) but still hand back the traceback so it can pivot. The cap is **per-step**,
not global, so one broken query doesn't burn the whole investigation budget.

## 7. Termination, two ways

- **Self-stop (the real one):** the model calls `finish`. *It* decided it was done.
  We ground the report and stop. There is no `if step == N: answer` anywhere.
- **Safety net:** if `step >= MAX_STEPS` or `tokens_used >= TOKEN_BUDGET`, we fire a
  visible `cap_hit` event and `_forced_finish` asks the model to write a report from
  only what it already has. This is the guard firing, not the agent deciding — and
  it's a *separate, visible* thing in the trace, so you can always tell a real
  self-stop from a budget stop.

How to tell them apart in the trace: a self-stop is `decision(finish) → report →
done` with **no** `cap_hit`. A budget stop has a `cap_hit` before the report.

## 8. Grounding + the decision log

- **Grounding (`grounding.py`):** `results_by_step` is a ledger of every result the
  model actually saw. Before we emit the report, `ground_check` walks each finding's
  `evidence_step` against that ledger and flags any claim that points at a step which
  produced no real result. "No result, no claim" — enforced in code, not just asked
  for in the prompt. A broken evidence link renders as broken in the UI, which is
  what proves the check is real.
- **The decision log IS the trace:** every `emit(...)` in the loop is both the live
  SSE event the browser renders and the log you'd debug from. There is no separate
  logging pass — the thing the demo shows and the thing you'd inspect are the same
  stream.

## 9. Prompt caching (cost)

The API is stateless, so every loop turn re-sends the whole conversation — system +
tools + *every prior turn*. Without caching you pay full input price for that growing
prefix on every step, and that's most of a run's cost. So before each
`messages.create` we set one `cache_control` breakpoint on the last block of the
latest turn (`_apply_prompt_cache` in `loop.py`). The API writes that prefix to a
cache once and re-reads it at **~0.1×** on every later turn. We keep exactly *one*
breakpoint (clearing the old one each turn) because the prefix grows and there's a
4-breakpoint limit. On Sonnet the cache only engages once the prefix passes ~2048
tokens — a couple of steps in, which is exactly when it starts to matter. Net effect:
a full investigation costs roughly half, with zero quality change.

## 10. Rate limiting (protecting a paid endpoint)

`/investigate` is public and calls a paid API — and CORS only stops *browsers* from
other origins; anyone can curl the backend directly. So `ratelimit.py` caps runs
**per IP per hour** and **globally per day** (a backstop against distributed abuse),
returning `429` *before any tokens are spent*; the viewer catches the 429 and offers
the recorded run. It's in-memory (the free backend is a single instance). The hard
dollar-backstop underneath it is a spend cap set in the Anthropic Console — the rate
limit is what stops one burst from draining that cap in an afternoon.

---

**The whiteboard test:** *"If a reviewer deleted every `if step ==` line, would it
still be an agent?"* — Yes. The forced first look becomes optional; the caps
disappear; but the model still hypothesizes, runs pandas, reads results, decides,
self-corrects, and finishes. The loop, not the scaffolding, is the agent.
