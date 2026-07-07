"""profile_data — always the agent's first move (Block 2).

The ORIENT step. Before the agent forms a single hypothesis it must LOOK at the
data, so it never invents a column that doesn't exist (the #1 failure mode). We
implement it as a pandas snippet run through the SAME sandbox as everything else,
so there is exactly one execution path.
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
