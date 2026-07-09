"""Central runtime configuration — every knob reads from the environment.

Kept dependency-free (plain ``os.getenv``) on purpose: this module is imported by
the sandbox child process, which must not drag in FastAPI or the Anthropic SDK.
"""
from __future__ import annotations

import os

_HERE = os.path.dirname(__file__)

# Load agent/.env for local dev. Guarded and optional. Note: the sandbox child
# never imports this module (and runs with a scrubbed env), so the API key loaded
# here can never leak into the sandbox.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_HERE, "..", ".env"))
except Exception:
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- LLM ----------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Live default = Sonnet (fast/cheap). Set MODEL=claude-opus-4-8 for higher quality.
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
MAX_OUTPUT_TOKENS = _int("MAX_OUTPUT_TOKENS", 8000)

# --- Loop caps (reliability) --------------------------------------------------
MAX_STEPS = _int("MAX_STEPS", 15)
MAX_RETRIES_PER_STEP = _int("MAX_RETRIES_PER_STEP", 3)
TOKEN_BUDGET = _int("TOKEN_BUDGET", 200_000)

# --- Sandbox limits -----------------------------------------------------------
SANDBOX_TIMEOUT_S = _int("SANDBOX_TIMEOUT_S", 10)     # wall-clock, universal floor
SANDBOX_CPU_S = _int("SANDBOX_CPU_S", 8)              # RLIMIT_CPU (portable)
SANDBOX_MEM_MB = _int("SANDBOX_MEM_MB", 512)          # RLIMIT_AS (Linux-enforced)
SANDBOX_MAX_CHARS = _int("SANDBOX_MAX_CHARS", 4000)   # bound result_repr / stdout

# --- Datasets -----------------------------------------------------------------
DATA_DIR = os.path.normpath(os.path.join(_HERE, "..", "data"))
DEMO_DATASET_ID = "demo:signups"
DEMO_DATASET_PATH = os.path.join(DATA_DIR, "signups.csv")

# --- Uploads (untrusted user CSVs) --------------------------------------------
UPLOAD_DIR = os.path.normpath(os.getenv("UPLOAD_DIR", os.path.join(_HERE, "..", "uploads")))
UPLOAD_MAX_BYTES = _int("UPLOAD_MAX_BYTES", 25 * 1024 * 1024)  # 25 MB
UPLOAD_TTL_S = _int("UPLOAD_TTL_S", 3600)

# --- Rate limiting (the public /investigate endpoint calls a paid API) --------
RATE_LIMIT_PER_IP_HOUR = _int("RATE_LIMIT_PER_IP_HOUR", 6)
RATE_LIMIT_GLOBAL_DAY = _int("RATE_LIMIT_GLOBAL_DAY", 150)

# --- CORS ---------------------------------------------------------------------
# Comma-separated. Includes localhost for dev; add the Vercel prod URL in prod.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
