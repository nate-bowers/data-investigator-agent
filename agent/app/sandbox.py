"""Isolated execution of ONE LLM-written pandas snippet.

Public API::

    run_pandas(code, df_path, *, chart=None, timeout_s=None, cpu_s=None,
               mem_mb=None, max_chars=None) -> SandboxResult

Why this exists: the agent writes its own pandas and we execute it. That is the
project's real risk surface, so the sandbox is built first and hard.

Isolation (v1 = subprocess; a container is the documented upgrade path — swap the
spawn internals behind this same signature):
  * the snippet runs in a CHILD process, so a crash/hang/OOM can't take down the
    FastAPI server;
  * resource limits are applied by the child on itself at startup (thread-safe —
    no ``preexec_fn``): RLIMIT_CPU (portable, SIGXCPU), RLIMIT_AS (Linux-enforced;
    a no-op on macOS — documented), RLIMIT_FSIZE;
  * a wall-clock timeout in the parent -> ``killpg`` the whole process group;
  * network denied two ways: ``unshare -n`` on Linux (kernel-level) + an in-child
    socket guard everywhere (the portable floor);
  * scrubbed minimal env, ``close_fds=True``, and the dataset passed by PATH — the
    data itself never crosses this boundary.

``SandboxResult`` is a plain dataclass whose fields are exactly the contract the
agent loop consumes (see the plan's "run_pandas result contract").
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Optional

from . import config

_RUNNER = os.path.join(os.path.dirname(__file__), "_sandbox_runner.py")


@dataclasses.dataclass
class SandboxResult:
    ok: bool
    result_repr: str = ""
    stdout: str = ""
    error: Optional[str] = None
    traceback: Optional[str] = None
    timed_out: bool = False
    duration_ms: int = 0
    chart_png: Optional[str] = None


def _probe_unshare() -> bool:
    """One-time capability probe: can we actually create a network namespace?

    Only true on Linux where ``unshare -n`` is present AND permitted (root or user
    namespaces). Elsewhere we fall back to the in-child socket guard.
    """
    if sys.platform != "linux":
        return False
    if shutil.which("unshare") is None:
        return False
    try:
        r = subprocess.run(["unshare", "-n", "true"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


_HAVE_UNSHARE = _probe_unshare()


def _scrubbed_env() -> dict[str, str]:
    """Minimal env for the child: no proxies, no credentials, no inherited config.

    A venv Python finds its own site-packages from its executable path, so pandas
    still imports without VIRTUAL_ENV. HOME/MPLCONFIGDIR point at /tmp so matplotlib
    has a writable cache dir.
    """
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": "/tmp",
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            proc.kill()
        except Exception:
            pass


def run_pandas(
    code: str,
    df_path: str,
    *,
    chart: Optional[dict[str, Any]] = None,
    timeout_s: Optional[int] = None,
    cpu_s: Optional[int] = None,
    mem_mb: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> SandboxResult:
    timeout_s = timeout_s or config.SANDBOX_TIMEOUT_S
    cpu_s = cpu_s or config.SANDBOX_CPU_S
    mem_mb = config.SANDBOX_MEM_MB if mem_mb is None else mem_mb
    max_chars = max_chars or config.SANDBOX_MAX_CHARS

    payload = json.dumps(
        {
            "code": code,
            "df_path": df_path,
            "chart": chart,
            "max_chars": max_chars,
            "cpu_s": cpu_s,
            "mem_mb": mem_mb,
        }
    )
    # Wrap in `unshare -n` on Linux so the snippet has no network namespace at all.
    cmd = (["unshare", "-n"] if _HAVE_UNSHARE else []) + [sys.executable, _RUNNER]

    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # own process group -> killpg the whole tree
            close_fds=True,
            env=_scrubbed_env(),
            text=True,
        )
    except Exception as e:  # spawn failure (should be rare)
        return SandboxResult(
            ok=False,
            error=f"failed to spawn sandbox: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    try:
        out, err = proc.communicate(input=payload, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:
            out, err = "", ""
        return SandboxResult(
            ok=False,
            timed_out=True,
            error=f"timed out after {timeout_s}s (wall clock)",
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    dur = int((time.monotonic() - start) * 1000)

    # The child writes exactly one JSON object (the SandboxResult) to real stdout;
    # user print() output was captured separately, so stdout is clean.
    parsed = None
    if out and out.strip():
        try:
            parsed = json.loads(out)
        except Exception:
            parsed = None

    if parsed is None:
        # No clean result -> the child was killed hard (kernel OOM, SIGXCPU, segfault).
        rc = proc.returncode
        cpu_killed = rc is not None and rc < 0 and -rc == int(signal.SIGXCPU)
        return SandboxResult(
            ok=False,
            timed_out=cpu_killed,
            error=f"sandbox exited abnormally (returncode={rc})",
            traceback=((err or "").strip()[: max_chars * 2] or None),
            duration_ms=dur,
        )

    return SandboxResult(
        ok=bool(parsed.get("ok")),
        result_repr=parsed.get("result_repr", ""),
        stdout=parsed.get("stdout", ""),
        error=parsed.get("error"),
        traceback=parsed.get("traceback"),
        chart_png=parsed.get("chart_png"),
        timed_out=False,
        duration_ms=dur,
    )
