# Data Investigator

Give it a dataset and an investigative question — *"why did signups drop in March?"*
— and it **investigates**. A hand-written agent loop hypothesizes, writes and runs
its own pandas, reads each result to decide the next move, **self-corrects broken
code from the traceback**, and stops when it has the answer. The path is not
hardcoded; the data drives it.

You watch it think: a live **investigation viewer** (not a chatbot) streams each
step — the reasoning, the code it wrote, the result, its decision to continue or
stop — and renders a **grounded final report** where every claim links to the step
whose result supports it.

## What it proves (the four things)

This is a demonstration of **agent orchestration**, not text-to-pandas. Every run
visibly shows all four:

1. **Runtime tool choice** — the LLM decides what to compute next; there is no
   hardcoded sequence. (In the demo run it chose *on its own* to segment by channel,
   then to check the campaign column.)
2. **A real loop** — each step's result informs the next.
3. **Self-termination** — the agent decides when it has answered (calls `finish`);
   the loop cap is a separate, visible safety net.
4. **Reliability under mess** — a broken query is caught, the verbatim traceback is
   fed back, and the model rewrites its own code.

## Architecture (split hosting)

```
Vercel · web/ (Next.js viewer)  ──POST /investigate──►  Backend · agent/ (FastAPI)
       ▲                                                    │ manual agent loop
       └──────── text/event-stream (SSE) ───────────────────┤ ├─► Anthropic API (Sonnet/Opus)
                 one step-event at a time                    │ └─► pandas sandbox (subprocess, no network)
```

- **`agent/`** — Python + FastAPI. The manual agentic loop (`app/loop.py`) over a
  3-tool surface, plus an isolated pandas sandbox that runs the LLM's code safely.
  Streams the decision log as step-level SSE.
- **`web/`** — Next.js investigation viewer, deployed as a portfolio section at
  `/investigator`. One reducer renders both live runs and a committed recorded run.
- **`docs/how-the-loop-works.md`** — the orchestration, explained end to end.

## How the agent works (the short version)

It's a `while` loop, not a sequence:

```
ask the model what to do  →  it emits a tool call  →  run the tool
      ↑                                                     │
      └───────────  feed the result back  ←─────────────────┘
```

Three tools: `profile_data` (forced first, so it never hallucinates a column),
`run_pandas` (the workhorse — writes a snippet, optionally chooses a chart), and
`finish` (the self-termination signal). A sandbox error returns the **verbatim
traceback** as a `tool_result` with `is_error: true`, and the model rewrites next
turn — that's the self-correction. Loop caps + a token budget prevent spirals;
grounding enforces "no result, no claim" in code. Full walkthrough in
[`docs/how-the-loop-works.md`](docs/how-the-loop-works.md).

## The sandbox (running untrusted, LLM-written code)

The agent writes its own pandas — and can run it over an uploaded CSV — so the
sandbox is the real safety boundary and was built first:

- **subprocess isolation** — a bad snippet dies as a child; the web server is never touched;
- **resource limits** — RLIMIT_CPU (portable) + RLIMIT_AS (Linux) + a wall-clock timeout → `killpg`;
- **no network** — `unshare -n` on Linux + an in-child socket guard everywhere;
- **bounded output + verbatim tracebacks** — big frames are summarized; errors come back whole for self-correction.

The dataset is passed by path; the data itself never crosses into the request body.
Container isolation is a one-file upgrade behind the same `run_pandas` contract.

## Repo layout

```
agent/            Python backend (FastAPI + agent loop + sandbox)
  app/loop.py       ★ the manual agentic loop
  app/tools.py      the 3 tool schemas
  app/prompts.py    the investigator system prompt
  app/sandbox.py    isolated pandas execution
  app/grounding.py  "no result, no claim"
  data/             the demo dataset + its seeder
  recordings/       the committed flawless run (demo insurance)
  tests/            sandbox (8) + mocked loop (4)
web/              Next.js investigation viewer
  lib/investigator/  events + reducer + the live/replay hook
  components/investigator/  StepCard, TraceStream, LoopMeter, QuestionBox, FinalReport
docs/             how-the-loop-works.md + the whiteboard quiz
```

## Run locally

```bash
# Backend
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add your ANTHROPIC_API_KEY
python data/generate_signups.py # (re)build the demo dataset
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd web
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
npm run dev                         # open http://localhost:3000/investigator
```

Model defaults to `claude-sonnet-4-6` (fast/cheap for a live click); set
`MODEL=claude-opus-4-8` for the strongest reasoning.

## Deploy

- **Backend → Fly.io** (or Railway/Koyeb): `fly launch --no-deploy`, then
  `fly secrets set ANTHROPIC_API_KEY=...`, then `fly deploy` (from `agent/`; a
  `Dockerfile` + `fly.toml` are included; always-on, no idle sleep).
- **Frontend → Vercel**: import the repo with **Root Directory = `web/`**, set
  `NEXT_PUBLIC_BACKEND_URL` to the backend URL.
- **CORS**: set `ALLOWED_ORIGINS` on the backend to your Vercel production URL.
- **Demo insurance**: `agent/recordings/signups-march-dip.json` is committed to
  `web/public/recordings/` and replays client-side, so a cold backend never breaks
  a live demo.

## Demo

Dataset: `agent/data/signups.csv` (~2,200 signups, Jan–Jun) with a planted,
non-obvious story — total signups dip in March, but only the **social** channel
collapses, and its `campaign_id` goes null that month (a paused campaign, not lost
demand). A few unparseable dates make the agent's first date-parse fail and
self-correct.

Ask **"Why did signups drop in March?"** and watch it hypothesize, hit a broken
query and fix itself, segment by channel, connect the collapse to the paused
campaign, chart the trend, and self-stop with a grounded answer.

> **The money line:** *"Here's the trace — it decided each step from the last
> result, caught its own error and fixed it, chose how to visualize the finding, and
> stopped when it had the answer. None of that path was hardcoded — the data drove
> it."*

## Tests

```bash
cd agent && python -m pytest      # sandbox isolation (8) + mocked agent loop (4)
```

## Design decisions

- **Manual loop, not the SDK tool-runner or Managed Agents** — hiding the loop
  would defeat the point; this repo *is* the orchestration, written to be read.
- **Chart choice is a field on `run_pandas`, not a separate tool** — it welds the
  chart to the result that motivated it and keeps the loop at three tools.
- **Grounding enforced in code** — every report claim references a real result, or
  it's flagged; a broken evidence link renders as broken.
- **Split hosting** — the viewer on Vercel, the CPU-bound agent + sandbox on an
  always-on Python host, the LLM behind an API.
