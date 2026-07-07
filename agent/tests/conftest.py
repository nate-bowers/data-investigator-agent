"""Shared test setup.

The sandbox child renders charts under MPLCONFIGDIR=/tmp. matplotlib's first run
there builds a font cache that is slow enough to collide with the sandbox CPU cap,
which would make the chart test flaky on a cold machine. Warm it once per session
so the sandbox tests are deterministic.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture(scope="session", autouse=True)
def _warm_matplotlib_cache():
    env = {**os.environ, "MPLCONFIGDIR": "/tmp", "MPLBACKEND": "Agg"}
    try:
        subprocess.run(
            [sys.executable, "-c", "import matplotlib.pyplot"],
            env=env,
            timeout=120,
            capture_output=True,
        )
    except Exception:
        pass
    yield
