"""Sandbox child process. Runs one LLM-written pandas snippet, then exits.

Lifecycle (all inside this short-lived process):
  1. read a JSON payload from stdin: {code, df_path, chart, max_chars, cpu_s, mem_mb}
  2. apply resource limits to *ourselves* (thread-safe; no preexec_fn needed)
  3. install the network guard
  4. load the dataset into ``df`` and ``exec`` the snippet
  5. write exactly one JSON SandboxResult to REAL stdout and exit

User ``print()`` output is captured into a buffer so it never corrupts the result
channel (which is real stdout). Keep this file importing only stdlib + pandas +
(lazily) matplotlib, no FastAPI, no anthropic.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import sys
import traceback


def _set_limits(cpu_s: int, mem_mb: int) -> None:
    """Cap the child so the kernel kills a runaway snippet.

    Set BEFORE importing pandas so the caps cover everything the snippet can reach.
    RLIMIT_AS is enforced on Linux and a silent no-op on macOS (documented).
    """
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
    except (ValueError, OSError):
        pass
    if mem_mb:
        # RLIMIT_AS caps VIRTUAL address space. numpy/OpenBLAS reserve a large
        # virtual space on Linux even when resident use is tiny, so a low cap kills
        # the pandas import outright (fine on macOS, where RLIMIT_AS is a no-op).
        # Floor it to a numpy-safe minimum; the real guards on a small box are the
        # OS OOM-killer plus the CPU + wall-clock limits.
        nbytes = max(mem_mb, 1536) * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (nbytes, nbytes))
        except (ValueError, OSError):
            pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (32 * 1024 * 1024, 32 * 1024 * 1024))
    except (ValueError, OSError):
        pass
    # Cap total processes for this UID so a snippet can't fork-bomb the box. 256 is
    # ample for single-threaded pandas/numpy but stops runaway spawning.
    nproc = getattr(resource, "RLIMIT_NPROC", None)
    if nproc is not None:
        try:
            resource.setrlimit(nproc, (256, 256))
        except (ValueError, OSError):
            pass
    # No core dumps: a segfault shouldn't write a large core file to the cwd.
    core = getattr(resource, "RLIMIT_CORE", None)
    if core is not None:
        try:
            resource.setrlimit(core, (0, 0))
        except (ValueError, OSError):
            pass


def _install_network_guard() -> None:
    """Portable floor: make network access raise inside the snippet.

    On Linux prod the real boundary is the network namespace (``unshare -n``); this
    guard is the cross-platform fallback (especially macOS dev). It is not a
    security boundary against hostile code. The code run here is our own LLM's
    output, not an attacker's.
    """
    import socket

    def _blocked(*_a, **_k):
        raise RuntimeError("network access is disabled in the sandbox")

    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]


def _bounded(text, max_chars: int) -> str:
    if text is None:
        return ""
    text = str(text)
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... [truncated {len(text) - max_chars} chars]"
    return text


def _repr_result(value, max_chars: int) -> str:
    """A compact, bounded repr of the result the model reads back.

    DataFrames/Series are summarized (shape + head) so a 100k-row frame can't blow
    the SSE payload or the model's context window.
    """
    import pandas as pd

    if value is None:
        return ""
    if isinstance(value, pd.DataFrame):
        return f"DataFrame shape={value.shape}\n{value.head(20).to_string()}"
    if isinstance(value, pd.Series):
        return f"Series len={len(value)} dtype={value.dtype}\n{value.head(20).to_string()}"
    return _bounded(repr(value), max_chars)


def _compile_capturing_last_expr(code: str):
    """Compile the snippet so that a trailing bare expression is captured as
    ``__lastexpr__`` (Jupyter-style). Lets the model end with ``df.groupby(...)``
    and still get a result even without an explicit ``result =``.

    Returns (code_or_codeobject, captured_last_expr: bool).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, False  # let exec() raise the SyntaxError -> clean traceback
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = tree.body[-1]
        assign = ast.Assign(
            targets=[ast.Name(id="__lastexpr__", ctx=ast.Store())],
            value=last.value,
        )
        ast.copy_location(assign, last)
        tree.body[-1] = assign
        ast.fix_missing_locations(tree)
        return compile(tree, "<snippet>", "exec"), True
    return code, False


def main() -> None:
    payload = json.loads(sys.stdin.read())
    code = payload["code"]
    df_path = payload["df_path"]
    chart_spec = payload.get("chart")
    max_chars = int(payload.get("max_chars", 4000))

    _set_limits(int(payload.get("cpu_s", 8)), int(payload.get("mem_mb", 512)))
    _install_network_guard()

    import pandas as pd

    result = {
        "ok": False,
        "result_repr": "",
        "stdout": "",
        "error": None,
        "traceback": None,
        "chart_png": None,
    }
    stdout_buf = io.StringIO()
    try:
        if df_path.endswith(".parquet"):
            df = pd.read_parquet(df_path)
        else:
            df = pd.read_csv(df_path)

        ns: dict = {"df": df, "pd": pd}
        compiled, captured_last = _compile_capturing_last_expr(code)
        with contextlib.redirect_stdout(stdout_buf):
            exec(compiled, ns)  # noqa: S102 (executing model-written code is intentional here)

        # Result: an explicit `result` var wins; otherwise the last bare expression.
        value = ns.get("result", ns.get("__lastexpr__") if captured_last else None)
        result["result_repr"] = _bounded(_repr_result(value, max_chars), max_chars)
        result["stdout"] = _bounded(stdout_buf.getvalue(), max_chars)

        # Optional chart, rendered from the result value, not the raw df.
        if chart_spec:
            try:
                from charts import render_chart  # sibling module (agent/app on sys.path)

                result["chart_png"] = render_chart(value, chart_spec)
            except Exception:
                result["chart_png"] = None  # a chart failure must not fail the step

        result["ok"] = True
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = _bounded(traceback.format_exc(), max_chars * 2)
        result["stdout"] = _bounded(stdout_buf.getvalue(), max_chars)

    # Bypass any stdout redirection and write only the JSON to the real channel.
    sys.__stdout__.write(json.dumps(result))
    sys.__stdout__.flush()


if __name__ == "__main__":
    main()
