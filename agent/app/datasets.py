"""Resolve a ``dataset_id`` to a local CSV path the sandbox can read.

  * ``"demo:signups"`` (or ``None``) -> the bundled demo dataset.
  * ``"upload:<token>"``             -> a user-uploaded CSV in ``UPLOAD_DIR``.

Uploaded CSVs are *untrusted* user input. Validation (size + parseability) happens
at upload time; the isolation that makes running LLM-written pandas over an arbitrary
uploaded CSV safe comes from the sandbox. The dataset is always passed to the sandbox
by PATH — never as inline data.
"""
from __future__ import annotations

import io
import os
import re
import time
import uuid

from . import config


_TOKEN_RE = re.compile(r"[a-f0-9]{12}")


def _upload_path(token: str) -> str:
    # Tokens are server-generated 12-char hex. Reject anything else outright (never
    # sanitize-and-continue) so a crafted dataset_id can't be shaped into a path
    # that escapes UPLOAD_DIR.
    if not _TOKEN_RE.fullmatch(token):
        raise ValueError(f"invalid dataset token: {token!r}")
    return os.path.join(config.UPLOAD_DIR, f"{token}.csv")


def resolve(dataset_id: str | None) -> str:
    """dataset_id -> absolute CSV path. Raises if unknown/missing."""
    if not dataset_id or dataset_id == config.DEMO_DATASET_ID:
        return config.DEMO_DATASET_PATH
    if dataset_id.startswith("upload:"):
        path = _upload_path(dataset_id.split(":", 1)[1])
        if not os.path.exists(path):
            raise FileNotFoundError(f"unknown dataset_id: {dataset_id}")
        return path
    raise ValueError(f"unknown dataset_id: {dataset_id!r}")


def save_upload(raw: bytes) -> str:
    """Validate that ``raw`` parses as CSV, persist it, and return its dataset_id."""
    # Parse a few rows to confirm it's really a CSV before we keep it.
    import pandas as pd

    pd.read_csv(io.BytesIO(raw), nrows=5)  # raises on garbage/binary
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    with open(_upload_path(token), "wb") as f:
        f.write(raw)
    return "upload:" + token


def describe(dataset_id: str | None) -> dict:
    """Columns + row count for the context panel, so the UI can show the dataset
    before the agent runs. Cheap given size-capped uploads."""
    import pandas as pd

    df = pd.read_csv(resolve(dataset_id))
    is_demo = not dataset_id or dataset_id == config.DEMO_DATASET_ID
    return {
        "name": "signups.csv" if is_demo else "your upload",
        "columns": [str(c) for c in df.columns],
        "rows": int(len(df)),
    }


def cleanup_expired() -> None:
    """Best-effort TTL sweep so uploaded CSVs don't accumulate on the box."""
    now = time.time()
    try:
        for name in os.listdir(config.UPLOAD_DIR):
            if name == ".gitkeep":
                continue
            p = os.path.join(config.UPLOAD_DIR, name)
            if now - os.path.getmtime(p) > config.UPLOAD_TTL_S:
                os.remove(p)
    except FileNotFoundError:
        pass
