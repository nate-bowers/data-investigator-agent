"""Render a chart from an agent-supplied spec.

The caller decides whether to chart and which kind + columns + reason; this
module just draws it. Charts are drawn from the step's result (the finding),
not the raw dataframe.

Returns a base64-encoded PNG string, which travels cleanly over SSE and inside
the recorded-run JSON with zero client-side charting dependency.
"""
from __future__ import annotations

import base64
import io
from typing import Any, Optional


def render_chart(value: Any, spec: dict[str, Any]) -> Optional[str]:
    import matplotlib

    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt
    import pandas as pd

    kind = spec.get("kind")
    x = spec.get("x")
    y = spec.get("y")
    reason = spec.get("reason") or ""

    fig, ax = plt.subplots(figsize=(6, 3.5), dpi=110)
    try:
        if isinstance(value, pd.Series):
            s = value
            if kind == "line":
                s.plot(ax=ax)
            elif kind == "bar":
                s.plot(kind="bar", ax=ax)
            elif kind == "hist":
                s.plot(kind="hist", ax=ax)
            elif kind == "scatter":
                ax.scatter(range(len(s)), s.values)
            else:
                plt.close(fig)
                return None
        elif isinstance(value, pd.DataFrame):
            d = value
            if kind == "scatter" and x and y:
                ax.scatter(d[x], d[y])
                ax.set_xlabel(x)
                ax.set_ylabel(y)
            elif kind == "line":
                (d.set_index(x)[y] if x and y else d).plot(ax=ax)
            elif kind == "bar":
                (d.set_index(x)[y] if x and y else d).plot(kind="bar", ax=ax)
            elif kind == "hist":
                (d[x] if x else d).plot(kind="hist", ax=ax)
            else:
                plt.close(fig)
                return None
        else:
            plt.close(fig)
            return None  # scalars / None aren't chartable

        if reason:
            ax.set_title(reason[:80])
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        plt.close(fig)
        return None
