"""The ground-truth eval suite.

Numeric and categorical reference answers are computed directly from the committed
CSVs (never hardcoded), so they cannot drift from the data. Causal reference answers
are short descriptions written by hand from each dataset's planted story; an LLM judge
compares them to the agent's report.

`forces_error=True` marks a question whose dataset has a non-numeric value in a numeric
column, so a naive computation raises and the agent must self-correct.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "data")
SIGNUPS = os.path.normpath(os.path.join(HERE, "..", "data", "signups.csv"))
SALES = os.path.join(DATA, "sales.csv")
SUPPORT = os.path.join(DATA, "support_tickets.csv")
TIPS = os.path.join(DATA, "tips.csv")


@dataclass
class EvalCase:
    id: str
    dataset_path: str
    dataset_label: str
    question: str
    kind: str  # "numeric" | "categorical" | "causal"
    reference: str
    tol: float = 0.0  # numeric only: allowed difference (absolute, or fraction if rel=True)
    rel: bool = False
    forces_error: bool = False


def _pct(mask) -> float:
    return round(float(mask.mean()) * 100, 1)


def build_suite() -> list[EvalCase]:
    sg = pd.read_csv(SIGNUPS)
    sl = pd.read_csv(SALES)
    sp = pd.read_csv(SUPPORT)
    tp = pd.read_csv(TIPS)

    sl_rev = float((sl["units"] * pd.to_numeric(sl["unit_price"], errors="coerce")).sum())

    return [
        # ---- signups (the planted demo dataset) ----
        EvalCase("sg_total", SIGNUPS, "signups", "How many total signups are in the dataset?",
                 "numeric", str(len(sg))),
        EvalCase("sg_channel", SIGNUPS, "signups",
                 "Which acquisition channel has the most signups overall?",
                 "categorical", sg["channel"].value_counts().idxmax()),
        EvalCase("sg_activated", SIGNUPS, "signups",
                 "What percentage of signups activated? Give a number.",
                 "numeric", str(_pct(sg["activated"] == "yes")), tol=1.5),
        EvalCase("sg_march", SIGNUPS, "signups", "Why did signups drop in March?", "causal",
                 "Only the social channel collapsed in March; its campaign_id went null because "
                 "the social campaign was paused. The other channels stayed roughly flat, so the "
                 "dip was a paused campaign, not a broad loss of demand.", forces_error=True),

        # ---- sales export ----
        EvalCase("sl_total", SALES, "sales", "How many orders are in the sales dataset?",
                 "numeric", str(len(sl))),
        EvalCase("sl_region", SALES, "sales", "Which region has the most orders?",
                 "categorical", sl["region"].value_counts().idxmax()),
        EvalCase("sl_revenue", SALES, "sales",
                 "What is the total revenue, computed as units times unit_price, across all orders?",
                 "numeric", str(round(sl_rev, 2)), tol=0.01, rel=True, forces_error=True),
        EvalCase("sl_sept", SALES, "sales", "Why did the number of orders fall in September?", "causal",
                 "The West region's orders collapsed in September (about 5 orders versus roughly 30 "
                 "in every other month). The other regions were stable, so the drop was specific to West."),

        # ---- support tickets ----
        EvalCase("sp_total", SUPPORT, "support_tickets", "How many support tickets are there?",
                 "numeric", str(len(sp))),
        EvalCase("sp_category", SUPPORT, "support_tickets", "Which ticket category is most common?",
                 "categorical", sp["category"].value_counts().idxmax()),
        EvalCase("sp_satisfied", SUPPORT, "support_tickets",
                 "What percentage of tickets ended with the customer satisfied?",
                 "numeric", str(_pct(sp["satisfied"] == "yes")), tol=1.5),
        EvalCase("sp_resolve", SUPPORT, "support_tickets",
                 "Which ticket category takes the longest to resolve on average?",
                 "categorical",
                 sp.assign(h=pd.to_numeric(sp["resolution_hours"], errors="coerce"))
                 .groupby("category")["h"].mean().idxmax(),
                 forces_error=True),

        # ---- restaurant tips ----
        EvalCase("tp_avgpct", TIPS, "tips",
                 "What is the average tip as a percentage of the total bill?",
                 "numeric", str(round(float((tp["tip"] / tp["total_bill"]).mean()) * 100, 1)), tol=1.5),
        EvalCase("tp_day", TIPS, "tips", "Which day has the most records?",
                 "categorical", tp["day"].value_counts().idxmax()),
        EvalCase("tp_party", TIPS, "tips",
                 "Do larger parties tend to leave a bigger tip as a percentage of the bill?", "causal",
                 "Yes. Tip percentage rises with party size, from about 16 percent for parties of 1 "
                 "to about 22 percent for parties of 6."),
    ]


if __name__ == "__main__":
    for c in build_suite():
        flag = " [error-trap]" if c.forces_error else ""
        print(f"{c.id:14s} {c.kind:11s} ref={c.reference[:70]!r}{flag}")
