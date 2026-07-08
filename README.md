# Data Investigator

**An autonomous data-analysis agent that investigates a dataset the way a person would — one question at a time, deciding each step from what the last one revealed.**

🔗 **Live demo → https://web-mu-three-lu56la822j.vercel.app/investigator**

I built Data Investigator to show that I can build a *real* agent from the ground up — not a single prompt that returns an answer, and not a framework wrapper, but a hand-written loop where a language model writes its own pandas, runs it in a sandbox, reads the result, and decides its next move. You hand it a dataset and an investigative question like *"why did signups drop in March?"* and you **watch it think**: hypothesize → run code → read the result → follow the lead → fix its own broken query → stop when it actually has the answer.

**Nothing about the path is hardcoded. The data drives it.** The UI is built to make that visible: you see the tools the agent can call, the columns it's looking at, and every tool call streaming in as `calls run_pandas → input → returned`.

> **Scope, honestly:** this is a *single* agent, done well end-to-end — designed, built, hardened, and deployed. The natural next chapter, turning it into genuine *multi-agent* orchestration, is sketched in the [Roadmap](#roadmap-from-one-agent-to-many).

---

## What it demonstrates

The whole point is a genuine **agent loop** — the model chooses its own control flow at runtime. Every run shows the four things that separate a real agent from a scripted pipeline:

| | |
|---|---|
| **Runtime tool choice** | the model decides what to compute next — there is no fixed sequence |
| **A real loop** | each step's result feeds the next decision |
| **Self-termination** | it decides when it has answered (and I can prove it wasn't a counter) |
| **Reliability under mess** | a broken query is caught, the traceback is fed back, and it rewrites its own code |

---

## The agent loop

The core is a hand-written `while` loop — deliberately not the SDK's tool-runner and not a managed-agent service, because the loop *is* the project and I wanted to own every line. Ask the model what to do, run whatever tool it asked for, feed the result back, repeat until it calls `finish`.

```mermaid
flowchart TD
    Q([Question + dataset]) --> P[profile_data<br/>look at the real columns first]
    P --> M{{Model decides the next move}}
    M -->|calls run_pandas| R[Run the pandas snippet<br/>in the sandbox]
    R -->|result or traceback| M
    M -->|calls finish| G[Ground every claim<br/>against a real result]
    G --> DONE([Answer + full trace])
```

The only move I force is the very first one — `profile_data`, so the agent sees the real schema before it hypothesizes and never invents a column. After that, `tool_choice` is `auto` and the model is on its own. When a snippet throws, the sandbox hands the **verbatim traceback** back as a tool result with `is_error: true`, and the model reads it and rewrites — that's the self-correction. **Delete every `if step ==` line in the loop and it's still an agent**; those lines are only the first-step nudge and the safety caps.

---

## Anatomy of a run

An actual run on the demo dataset (*"why did signups drop in March?"*) — the reasoning path the agent chose entirely on its own:

```
① profile_data      → sees signup_date / campaign_id / activated are strings, 2,224 rows
② run_pandas        → monthly totals … ValueError: date "unknown" won't parse
   └─ self-corrects → re-runs with errors='coerce' → confirms the March dip
③ run_pandas        → signups by channel × month … only `social` collapses in March
④ run_pandas        → social by campaign_id … cmp_social_2024 is absent all March
⑤ run_pandas + bar  → weekly social signups, Feb vs Mar → chart shows a hard stop
⑥ finish            → "the social campaign was paused" — 6 findings, each grounded
```

It hit a broken date parse and fixed itself (②), branched from *total* → *channel* → *campaign* because each result pointed there, **chose** to draw a chart, and stopped once the causal chain held. A committed recording of this exact run replays on the live page even when the free backend is asleep.

---

## Architecture

Split hosting: a static viewer on Vercel, the CPU-bound agent + sandbox on an always-on Python host, the model behind an API.

```mermaid
flowchart TD
    V["Viewer — Next.js on Vercel"]
    V -->|POST /investigate| L["Agent loop — FastAPI on Render"]
    L -.->|SSE: live decision trace| V
    L -->|run_pandas| S["pandas sandbox<br/>subprocess · no network"]
    L -->|tool calls| C["Claude Sonnet 4.6 — Anthropic API"]
```

The backend streams its **decision log** as step-level Server-Sent Events — the same stream the UI renders live and the thing I'd debug from. There's no separate logging pass; the trace *is* the log.

---

## Running LLM-written code safely (the sandbox)

The agent writes and runs its own pandas — including over an uploaded CSV — so the sandbox is the real risk surface, and I built it first:

- **Subprocess isolation** — a bad snippet dies as a child; the web server is never touched.
- **Resource limits** — `RLIMIT_CPU` + `RLIMIT_AS` (floored so numpy still imports on Linux) + a wall-clock timeout that `killpg`s the whole process group.
- **No network** — `unshare -n` on Linux plus an in-process socket guard everywhere.
- **Bounded output, verbatim tracebacks** — big frames are summarized to a head + shape; errors come back *whole*, which is exactly the fuel the self-correction loop needs.

The dataset is passed by path; the data never crosses into the request body. Swapping the subprocess for a locked-down container is a one-file change behind the same `run_pandas` contract.

---

## Reliability & cost

Built in from the start, not bolted on:

- **Grounding** — every claim in the final report must reference a step that produced a real result. Enforced in code (`grounding.py`), not just asked for in the prompt; a broken evidence link renders as broken in the UI.
- **Loop cap + token budget** — checked before every model call, so a run can't spiral or overspend.
- **Prompt caching** — one cache breakpoint follows the growing conversation prefix, so tools + system + prior turns are re-read at ~0.1×. Roughly halves the cost of a run with zero quality change.
- **Rate limiting** — the public `/investigate` endpoint is capped per-IP and globally per day (returns `429` before any tokens are spent), with an Anthropic Console spend cap as the hard backstop.

---

## Engineering highlights

What this project shows I can do:

- **Ship a full-stack AI product end-to-end** — designed, built, and deployed a typed FastAPI backend and a Next.js/TypeScript frontend, split-hosted on Render + Vercel with CORS, secrets management, and a live streaming API.
- **Build the hard part myself** — a hand-written agentic loop instead of a framework, so I understand the tool-use handshake, self-correction, and termination at the token level.
- **Take security seriously** — a genuine sandbox for executing untrusted, model-generated code (isolation, resource limits, no network).
- **Engineer for reliability** — grounding, loop/token caps, and self-correction so the system can't hallucinate conclusions or run away.
- **Engineer for cost** — prompt caching and rate limiting to keep a public, paid endpoint cheap and safe.
- **Test what matters** — pytest over the sandbox isolation, the mocked agent loop, and the rate limiter.

---

## Roadmap: from one agent to many

The obvious next step — and the reason the architecture is factored the way it is — is to turn this single agent into a small **orchestrated team**, reusing the exact loop above as the worker:

1. **Coordinator** — decomposes the question into angles ("is the drop real?", "which segment?", "is it a data artifact?").
2. **Parallel investigators** — fans out N copies of the current loop, each investigating one angle at the same time.
3. **Critic** — a verifier agent that adversarially tries to refute each finding before it's trusted.
4. **Synthesizer** — merges the grounded findings into one report that cites which agent found what.

That's the jump from "a well-built agent" to genuine multi-agent orchestration (decompose → parallel map → verify → reduce), with a designed role for each agent.

**Other next steps I'd take toward production:** containerize the sandbox (`docker --network=none --pids-limit`), add tracing + an eval harness to measure investigation quality over time, per-user auth for private datasets, a job queue for long runs, and a custom domain.

---

## Tech stack

- **Backend** — Python 3.12, FastAPI, the Anthropic Python SDK (Claude **Sonnet 4.6**), pandas, matplotlib. A hand-written agentic loop; a subprocess sandbox. Deployed on **Render**.
- **Frontend** — Next.js 15 (App Router) + React 19 + TypeScript. One reducer renders both live runs and the recorded run. Deployed on **Vercel**.
- **Design notes** — a fuller writeup of how the loop works is in [`docs/how-the-loop-works.md`](docs/how-the-loop-works.md).

---

## Run it locally

```bash
# Backend
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                # add your ANTHROPIC_API_KEY
python data/generate_signups.py     # (re)build the demo dataset
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd web
npm install
cp .env.local.example .env.local    # NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
npm run dev                          # → http://localhost:3000/investigator
```

Tests: `cd agent && python -m pytest` — sandbox isolation, the mocked agent loop, and the rate limiter.

---

## Project layout

```
agent/            Python backend
  app/loop.py       the hand-written agentic loop (the heart of it)
  app/tools.py      the 3 tool schemas the model sees
  app/sandbox.py    isolated pandas execution
  app/grounding.py  "no result, no claim"
  data/             the demo dataset + its seeder
  recordings/       the committed flawless run (demo insurance)
web/              Next.js viewer
  lib/investigator/         events + reducer + the live/replay hook
  components/investigator/  the context panel, step cards, loop meter, report
docs/             how-the-loop-works.md
```
