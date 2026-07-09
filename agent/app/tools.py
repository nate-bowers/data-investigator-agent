"""The agent's tool surface: three tools.

Each tool is a JSON schema the model sees and chooses among at runtime.

  profile_data()  -> inspect the data (forced first)
  run_pandas()    -> test one hypothesis with a pandas snippet, optionally
                     attaching a chart to visualize the finding
  finish()        -> declare the question answered
"""
from __future__ import annotations

PROFILE_DATA = {
    "name": "profile_data",
    "description": (
        "Profile the dataset: shape, columns, dtypes, null counts, and sample rows. "
        "Call this FIRST, before forming any hypothesis, so you never reference a "
        "column that does not exist. Takes no arguments."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

RUN_PANDAS = {
    "name": "run_pandas",
    "description": (
        "Run a short pandas snippet to test ONE hypothesis about the question. The "
        "dataset is preloaded as a DataFrame named `df`. Put your answer in a variable "
        "named `result` (or end with a bare expression, or print()). State does NOT "
        "persist between calls: each snippet is independent, so recompute what you "
        "need. If the snippet errors you get the full traceback back: read it and fix "
        "your code. Optionally attach a chart to visualize THIS result when a picture "
        "communicates the finding better than a number."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "hypothesis": {
                "type": "string",
                "description": "The specific sub-question this snippet tests, in one sentence.",
            },
            "code": {
                "type": "string",
                "description": "A pandas snippet operating on `df`. Assign to `result` and/or print().",
            },
            "chart": {
                "type": "object",
                "description": (
                    "OPTIONAL. Include ONLY when this result is worth visualizing; omit it "
                    "entirely when a sentence is enough (a single number needs no chart). "
                    "The chart is drawn from your `result`."
                ),
                "properties": {
                    "kind": {"type": "string", "enum": ["line", "bar", "hist", "scatter"]},
                    "reason": {
                        "type": "string",
                        "description": "Why this chart, in one phrase (e.g. 'bar: comparison across 5 channels').",
                    },
                    "x": {"type": "string", "description": "Optional x-axis column (DataFrame results)."},
                    "y": {"type": "string", "description": "Optional y-axis column (DataFrame results)."},
                },
                "required": ["kind", "reason"],
            },
        },
        "required": ["hypothesis", "code"],
    },
}

FINISH = {
    "name": "finish",
    "description": (
        "Call this when you have actually answered the question, not before. Give a "
        "clear written answer plus a list of findings, each tied to the step whose "
        "result supports it. Every claim must reference a real result you computed; if "
        "you cannot ground it, do not claim it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "The final answer to the question, in a few sentences.",
            },
            "findings": {
                "type": "array",
                "description": "The evidence chain: one claim + the step number whose result supports it.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "evidence_step": {
                            "type": "integer",
                            "description": "The step number whose result supports this claim.",
                        },
                    },
                    "required": ["claim", "evidence_step"],
                },
            },
        },
        "required": ["answer", "findings"],
    },
}

TOOLS = [PROFILE_DATA, RUN_PANDAS, FINISH]
