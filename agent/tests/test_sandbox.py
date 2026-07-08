"""The 7-case sandbox test plan (build plan Block 1).

Proves the isolation guarantees hold: a clean run works, a broken snippet returns
a verbatim traceback (the self-correction fuel), output is bounded, wall-clock and
CPU runaways are killed, memory is capped (Linux), the network is denied, and a
requested chart renders.
"""
from __future__ import annotations

import sys

import pandas as pd
import pytest

from app.sandbox import run_pandas


@pytest.fixture()
def df_path(tmp_path):
    p = tmp_path / "data.csv"
    pd.DataFrame(
        {
            "g": ["a", "a", "b", "b", "c"],
            "v": [1, 2, 3, 4, 5],
        }
    ).to_csv(p, index=False)
    return str(p)


def test_clean_success(df_path):
    r = run_pandas("result = int(df['v'].sum())", df_path)
    assert r.ok
    assert "15" in r.result_repr
    assert r.error is None and r.traceback is None


def test_last_expression_is_the_result(df_path):
    # No explicit `result =` — the trailing expression becomes the result.
    r = run_pandas("df.groupby('g')['v'].sum()", df_path)
    assert r.ok
    assert "Series" in r.result_repr


def test_traceback_verbatim_on_error(df_path):
    r = run_pandas("df['does_not_exist']", df_path)
    assert not r.ok
    assert r.traceback is not None
    assert "KeyError" in r.traceback  # the model reads this to fix itself


def test_output_is_bounded(df_path):
    r = run_pandas("print('x' * 100000)\nresult = 1", df_path, max_chars=4000)
    assert r.ok
    assert len(r.stdout) <= 4000 + 200  # bounded + truncation note


def test_wall_clock_timeout(df_path):
    # sleep() burns no CPU, so this exercises the parent's wall-clock kill path.
    r = run_pandas("import time; time.sleep(5)", df_path, timeout_s=1)
    assert not r.ok
    assert r.timed_out


def test_cpu_runaway_is_killed(df_path):
    # A busy loop burns CPU -> RLIMIT_CPU (SIGXCPU) kills it before wall clock.
    r = run_pandas("while True:\n    pass", df_path, cpu_s=1, timeout_s=20)
    assert not r.ok  # killed one way or another (SIGXCPU or wall clock)


def test_network_is_denied(df_path):
    r = run_pandas("import socket; socket.socket()", df_path)
    assert not r.ok
    assert "network access is disabled" in (r.traceback or "")


@pytest.mark.skipif(sys.platform == "darwin", reason="RLIMIT_AS is not enforced on macOS")
def test_memory_cap_linux(df_path):
    # RLIMIT_AS is floored to a numpy-safe minimum (1536MB), so allocate above that.
    r = run_pandas("x = bytearray(2200 * 1024 * 1024)", df_path, mem_mb=2048)
    assert not r.ok  # MemoryError under the address-space cap


def test_chart_renders_base64_png(df_path):
    r = run_pandas(
        "result = df.groupby('g')['v'].sum()",
        df_path,
        chart={"kind": "bar", "reason": "sum of v by group"},
    )
    assert r.ok
    assert r.chart_png and len(r.chart_png) > 100
