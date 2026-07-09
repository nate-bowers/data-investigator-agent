"""Generate the sample dataset with a planted, non-obvious story.

Deterministic (fixed seed) so runs are reproducible.

The story to uncover from "why did signups drop in March?":
  * total signups dip in March;
  * the dip is not uniform — only the `social` channel collapses in March
    (organic / paid_search / referral stay flat);
  * social's collapse coincides with campaign_id going null for social rows in
    March — a paused campaign, not lost demand;
  * social recovers in April.

Red herring: `activated` is stored as the strings "yes"/"no" (as messy CSVs often
are — and unlike "true"/"false", pandas does not coerce these to bool), so a naive
activation-rate query (`.mean()`) throws a TypeError. `signup_date` is a plain
string AND a few rows hold the unparseable value "unknown", so a first
`pd.to_datetime(...)` raises until it adds errors='coerce'.

Run:  python agent/data/generate_signups.py
"""
from __future__ import annotations

import csv
import math
import os
import random

CHANNELS = ["organic", "paid_search", "referral", "social"]
COUNTRIES = ["US", "UK", "CA", "DE", "IN"]
DEVICES = ["mobile", "desktop"]


def _daily_rate(channel: str, month: int) -> float:
    base = {"organic": 4.0, "paid_search": 3.0, "referral": 2.0, "social": 4.0}[channel]
    if channel == "social" and month == 3:  # paused campaign in March
        return 0.5
    return base


def _campaign_id(channel: str, month: int) -> str:
    if channel == "paid_search":
        return "cmp_ps_2024"
    if channel == "social":
        return "" if month == 3 else "cmp_social_2024"  # "" -> NaN for social rows in March
    return ""  # organic / referral run no campaign


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's small-lambda Poisson sampler."""
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1


def main() -> None:
    rng = random.Random(42)
    rows = []
    uid = 1000
    from datetime import date, timedelta

    start = date(2024, 1, 1)
    for i in range(182):  # Jan 1 – Jun 30
        d = start + timedelta(days=i)
        for ch in CHANNELS:
            for _ in range(_poisson(rng, _daily_rate(ch, d.month))):
                uid += 1
                # Activation ~0.55, with a mild March wobble (the red herring).
                p_act = 0.50 if d.month == 3 else 0.56
                rows.append(
                    {
                        "signup_date": d.isoformat(),
                        "user_id": f"u{uid}",
                        "channel": ch,
                        "campaign_id": _campaign_id(ch, d.month),
                        "country": rng.choices(COUNTRIES, weights=[5, 2, 2, 1, 3])[0],
                        "device": rng.choices(DEVICES, weights=[6, 4])[0],
                        "activated": "yes" if rng.random() < p_act else "no",
                    }
                )

    # Inject a handful of unparseable dates (messy real-world data). A first
    # `pd.to_datetime(...)` raises until it adds errors='coerce'.
    # Placed away from the top so a head(5) sample still looks clean.
    for idx in rng.sample(range(60, len(rows)), 8):
        rows[idx]["signup_date"] = "unknown"

    out = os.path.join(os.path.dirname(__file__), "signups.csv")
    cols = ["signup_date", "user_id", "channel", "campaign_id", "country", "device", "activated"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
