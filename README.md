# Data Investigator

An **agent-orchestration** demo: give it a dataset and an investigative question
("why did signups drop in March?") and it *investigates* — a hand-written agent
loop that hypothesizes, writes and runs its own pandas, reads each result to
decide the next move, **self-corrects broken code from the traceback**, and stops
when it has the answer. The path is not hardcoded; the data drives it.

You watch it think: a live **investigation viewer** (not a chatbot) streams each
step — hypothesis → the code it wrote → the result → its decision to continue or
stop — and renders a grounded final report where every claim traces to a real
computation.

## What it proves (the four things)

1. **Runtime tool choice** — the LLM decides what to compute next, not a fixed sequence.
2. **A real loop** — each step's result informs the next.
3. **Self-termination** — the agent decides when it has answered.
4. **Reliability under mess** — a broken query is caught, fed back, and corrected.

## Architecture (split hosting)

```
Vercel (web/, Next.js viewer)  ──POST /investigate──►  Backend (agent/, FastAPI)
        ▲                                                   │ manual agent loop
        └──────── text/event-stream (SSE) ──────────────────┤ ├─► Anthropic API
                  one step-event at a time                  │ └─► pandas sandbox (subprocess, no net)
```

- `agent/` — Python + FastAPI: the manual agentic loop + the isolated pandas sandbox.
- `web/` — Next.js investigation viewer, deployed as a portfolio section at `/investigator`.
- `docs/how-the-loop-works.md` — how the orchestration works, end to end.

See the build plan and design decisions below (filled in at Block 8).

## Run locally

```bash
# Backend
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd web
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
npm run dev
```
