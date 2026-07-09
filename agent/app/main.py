"""FastAPI entrypoint: the HTTP shell around the agent loop.

Endpoints:
  GET  /health       liveness + which model is configured
  POST /investigate  runs the agent loop, streams the decision log as SSE
  POST /upload       accept a user CSV, return a dataset_id

The agent loop itself lives in ``app/loop.py``. This module only wires
HTTP + CORS + streaming, keeping the orchestration logic in one place.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import config, datasets, loop, tools
from .events import SSEEmitter
from .loop import ModelUnavailable
from .ratelimit import cheap_limiter, limiter


def _warm_matplotlib_cache() -> None:
    """Build matplotlib's font cache off the request path.

    The sandbox child renders charts under MPLCONFIGDIR=/tmp; matplotlib's first
    run there builds a font cache that is slow enough to collide with the sandbox
    CPU cap. Warming it at startup means the first real chart render is fast.
    Best-effort and detached: never blocks startup.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp",
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": "/tmp",
    }
    try:
        subprocess.Popen(
            [sys.executable, "-c", "import matplotlib.pyplot"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


async def _upload_sweeper() -> None:
    """Sweep expired uploads at startup and every ~600s thereafter, so user CSVs
    don't accumulate on the box between /upload calls. Best-effort: a failure in
    one pass never crashes the loop."""
    while True:
        try:
            datasets.cleanup_expired()
        except Exception:
            pass
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warm_matplotlib_cache()
    sweeper = asyncio.create_task(_upload_sweeper())
    yield
    sweeper.cancel()


app = FastAPI(title="Data Investigator", lifespan=lifespan)

# CORS: the browser bundle on Vercel talks cross-origin to this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Headers that keep the SSE stream un-buffered end to end.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/Fly)
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": config.MODEL, "build": "context-panel-1"}


def _client_ip(request: Request) -> str:
    # Behind Render's single proxy the trusted client IP is the RIGHTMOST
    # X-Forwarded-For hop (the one the proxy itself appended); the leftmost hop is
    # caller-controlled and trivially spoofable, so never trust it for rate limiting.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _first_sentence(text: str) -> str:
    return text.split(". ")[0].rstrip(".") + "."


@app.get("/context")
def context(request: Request, dataset_id: str | None = None) -> dict:
    """Return what goes into the agent: the tools it can call + the dataset schema.
    Powers the viewer's context panel so the agent's capabilities and the data are
    visible before it runs (and after a CSV upload)."""
    allowed, reason = cheap_limiter.allow(_client_ip(request))
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    try:
        dataset = datasets.describe(dataset_id)
    except Exception:
        dataset = None
    return {
        "tools": [
            {"name": t["name"], "description": _first_sentence(t["description"])} for t in tools.TOOLS
        ],
        "dataset": dataset,
    }


class InvestigateRequest(BaseModel):
    question: str = Field(..., max_length=2000)  # 422 before any tokens are spent
    dataset_id: str | None = None  # None -> the bundled demo dataset


@app.post("/investigate")
def investigate(req: InvestigateRequest, request: Request) -> StreamingResponse:
    """Run the agent loop and stream its decision log as SSE.

    This is a *sync* endpoint on purpose: the agent loop makes blocking calls (the
    Anthropic SDK + the pandas sandbox subprocess), and Starlette runs sync path
    operations (and iterates the sync generator below) in a threadpool, so the
    event loop is never blocked.
    """
    # Throttle before spending any API tokens.
    allowed, reason = limiter.allow(_client_ip(request))
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    run_id = "inv_" + uuid.uuid4().hex[:10]
    try:
        df_path = datasets.resolve(req.dataset_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    emitter = SSEEmitter(run_id)

    def gen():
        try:
            yield from loop.run_investigation(req.question, df_path, emitter)
        except ModelUnavailable as e:  # rate-limited/overloaded: surface the reason
            print(f"[investigate] run {run_id} model unavailable: {e!r}", file=sys.stderr, flush=True)
            yield emitter.error(-1, str(e))
            yield emitter.done(-1, "error")
        except Exception as e:  # surface a terminal failure so the UI never hangs
            print(f"[investigate] run {run_id} failed: {e!r}", file=sys.stderr, flush=True)
            yield emitter.error(-1, "investigation failed (internal error)")
            yield emitter.done(-1, "error")

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a user CSV, validate it, persist it, return its dataset_id.

    The returned dataset_id is passed back to /investigate. The uploaded data is
    untrusted, but it only ever runs inside the sandbox, never here.
    """
    allowed, reason = cheap_limiter.allow(_client_ip(request))
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)
    # Read in bounded chunks and abort as soon as we exceed the cap, so a huge
    # upload can't be loaded into memory in one shot on a small instance.
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf += chunk
        if len(buf) > config.UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail="file too large")
    raw = bytes(buf)
    try:
        dataset_id = datasets.save_upload(raw)
    except Exception as e:  # not a parseable CSV
        raise HTTPException(status_code=400, detail=f"not a valid CSV: {e}")
    datasets.cleanup_expired()
    return {"dataset_id": dataset_id}
