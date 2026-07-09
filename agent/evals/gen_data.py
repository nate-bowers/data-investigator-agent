"""Generate deterministic eval datasets with known ground truth.

Each dataset is seeded (fixed RNG) so the CSVs and their computed reference answers
are reproducible. Some numeric columns contain a few non-numeric values ("unknown",
"pending") on purpose: they force the agent to hit a traceback and self-correct,
which is what the self-correction eval measures.

Run:  python -m evals.gen_data   (writes agent/evals/data/*.csv)
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, "data")

# Region order-counts per month. September collapses the West region (the planted
# story for "why did revenue fall in September?").
_SALES_BASE = {"North": 40, "South": 30, "East": 30, "West": 30}
_SALES_SEPT = {"North": 40, "South": 30, "East": 30, "West": 5}


def _sales() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    cats = ["A", "B", "C"]
    for month in range(1, 13):
        counts = _SALES_SEPT if month == 9 else _SALES_BASE
        for region, n in counts.items():
            for _ in range(n):
                day = int(rng.integers(1, 28))
                rows.append(
                    {
                        "order_date": f"2024-{month:02d}-{day:02d}",
                        "region": region,
                        "category": cats[int(rng.integers(0, 3))],
                        "product": f"P{int(rng.integers(1, 7))}",
                        "units": int(rng.integers(1, 21)),
                        "unit_price": round(float(rng.uniform(10, 200)), 2),
                    }
                )
    df = pd.DataFrame(rows).sample(frac=1.0, random_state=11).reset_index(drop=True)
    # Error trap: 20 rows get a non-numeric unit_price so a naive revenue calc raises.
    df["unit_price"] = df["unit_price"].astype(object)
    trap_idx = df.sample(n=20, random_state=7).index
    df.loc[trap_idx, "unit_price"] = "unknown"
    return df


def _support() -> pd.DataFrame:
    rng = np.random.default_rng(23)
    n = 1200
    # billing is the most common category (planted mode).
    category = rng.choice(
        ["billing", "technical", "account", "other"], size=n, p=[0.4, 0.25, 0.2, 0.15]
    )
    # technical tickets take far longer to resolve (planted story).
    means = {"billing": 8.0, "technical": 40.0, "account": 12.0, "other": 6.0}
    hours = np.array([max(0.5, rng.normal(means[c], means[c] * 0.25)) for c in category]).round(1)
    df = pd.DataFrame(
        {
            "created_date": [f"2024-{int(rng.integers(1,13)):02d}-{int(rng.integers(1,28)):02d}" for _ in range(n)],
            "category": category,
            "priority": rng.choice(["low", "medium", "high"], size=n, p=[0.5, 0.35, 0.15]),
            "resolution_hours": hours,
            "satisfied": rng.choice(["yes", "no"], size=n, p=[0.7, 0.3]),
        }
    )
    # Error trap: 15 tickets are still open, so resolution_hours is a string.
    df["resolution_hours"] = df["resolution_hours"].astype(object)
    trap_idx = df.sample(n=15, random_state=3).index
    df.loc[trap_idx, "resolution_hours"] = "pending"
    return df


def _tips() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    n = 300
    total_bill = np.clip(rng.normal(20, 8, n), 3, None).round(2)
    party = rng.integers(1, 7, n)
    # Tip rate rises with party size (planted story), plus noise.
    rate = 0.15 + 0.012 * party + rng.normal(0, 0.02, n)
    tip = np.clip(total_bill * rate, 0.5, None).round(2)
    df = pd.DataFrame(
        {
            "total_bill": total_bill,
            "tip": tip,
            "sex": rng.choice(["Male", "Female"], size=n),
            "smoker": rng.choice(["yes", "no"], size=n, p=[0.35, 0.65]),
            # Saturday is the most common day (planted mode).
            "day": rng.choice(["Thu", "Fri", "Sat", "Sun"], size=n, p=[0.2, 0.2, 0.4, 0.2]),
            "time": rng.choice(["Lunch", "Dinner"], size=n, p=[0.35, 0.65]),
            "party_size": party,
        }
    )
    return df


BUILDERS = {"sales": _sales, "support_tickets": _support, "tips": _tips}


def build_all() -> dict[str, str]:
    """Write every generated dataset to agent/evals/data and return {name: path}."""
    os.makedirs(DATA_DIR, exist_ok=True)
    paths = {}
    for name, fn in BUILDERS.items():
        path = os.path.join(DATA_DIR, f"{name}.csv")
        fn().to_csv(path, index=False)
        paths[name] = path
    return paths


if __name__ == "__main__":
    for name, path in build_all().items():
        df = pd.read_csv(path)
        print(f"{name:16s} {len(df):5d} rows  cols={list(df.columns)}")
