"""profile_data — the agent's first move.

Profiles the data before the agent forms a hypothesis, so it doesn't reference a
column that doesn't exist. Implemented as a pandas snippet run through the same
sandbox as everything else, so there is exactly one execution path.
"""
from __future__ import annotations


def profile_snippet() -> str:
    """pandas that prints a compact profile — shape, columns + dtypes, null counts,
    and a few sample rows. Runs in the sandbox against the preloaded ``df``."""
    return (
        "print('shape:', df.shape)\n"
        "print()\n"
        "print('columns / dtypes:')\n"
        "print(df.dtypes)\n"
        "print()\n"
        "print('null counts:')\n"
        "print(df.isnull().sum())\n"
        "print()\n"
        "print('sample rows:')\n"
        "print(df.head(5).to_string())\n"
    )
