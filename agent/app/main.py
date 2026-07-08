"""FastAPI entrypoint — the thin HTTP shell around the agent loop.

Endpoints:
  GET  /health       liveness + which model is configured
  POST /investigate  runs the agent loop, streams the decision log as SSE
  POST /upload       (Block 1b) accept a user CSV, return a dataset_id

The agent loop itself lives in ``app/loop.py`` (Block 3). This module only wires
HTTP + CORS + streaming; it stays deliberately thin so the orchestration logic is
all in one readable place.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import config, datasets, loop
from .events import SSEEmitter
from .ratelimit import limiter


def _warm_matplotlib_cache() -> None:
    """Build matplotlib's font cache off the request path.

    The sandbox child renders charts under MPLCONFIGDIR=/tmp; matplotlib's first
    run there builds a font cache that is slow enough to collide with the sandbox
    CPU cap. Warming it at startup means the first real chart render is fast.
    Best-effort and detached — never blocks startup.
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warm_matplotlib_cache()
    yield


app = FastAPI(title="Data Investigator", lifespan=lifespan)

# CORS: the browser bundle on Vercel talks cross-origin to this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Headers that keep the SSE stream un-buffered end to end.
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/Fly)
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": config.MODEL, "build": "rate-limit-cache-1"}


def _client_ip(request: Request) -> str:
    # Behind Render's proxy the real client is in X-Forwarded-For (first hop).
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class InvestigateRequest(BaseModel):
    question: str
    dataset_id: str | None = None  # None -> the bundled demo dataset


@app.post("/investigate")
def investigate(req: InvestigateRequest, request: Request) -> StreamingResponse:
    """Run the agent loop and stream its decision log as SSE.

    This is a *sync* endpoint on purpose: the agent loop makes blocking calls (the
    Anthropic SDK + the pandas sandbox subprocess), and Starlette runs sync path
    operations — and iterates the sync generator below — in a threadpool, so the
    event loop is never blocked. Keeping the loop synchronous keeps it readable.
    """
    # Throttle before spending any API tokens (429 -> the viewer offers the recording).
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
        except Exception as e:  # surface a terminal failure so the UI never hangs
            yield emitter.error(-1, f"investigation failed: {e}")
            yield emitter.done(-1, "error")

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, str]:
    """Accept a user CSV, validate it, persist it, return its dataset_id.

    The returned dataset_id is passed back to /investigate. The uploaded data is
    untrusted — but it only ever runs inside the sandbox, never here.
    """
    raw = await file.read()
    if len(raw) > config.UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        dataset_id = datasets.save_upload(raw)
    except Exception as e:  # not a parseable CSV
        raise HTTPException(status_code=400, detail=f"not a valid CSV: {e}")
    datasets.cleanup_expired()
    return {"dataset_id": dataset_id}
