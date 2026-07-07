"""Loop invariants, tested with a MOCKED Anthropic client (no API calls, no key).

These lock down the mechanics that must not regress:
  * the assistant turn is appended before its tool_result (the API handshake);
  * a sandbox error comes back as is_error=True and drives a retry (self-correction);
  * the loop cap halts a model that never finishes (reliability);
  * grounding flags a claim whose evidence_step produced no real result.

The real sandbox runs here (small snippets), so this doubles as integration.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app import config
from app.events import SSEEmitter
from app.loop import run_investigation


# --- a tiny fake Anthropic client ----------------------------------------------


class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


def tool_use(name, inp, id="t"):
    return _Block("tool_use", name=name, input=inp, id=id)


class _Usage:
    input_tokens = 10
    output_tokens = 10


class _Resp:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class FakeClient:
    """Returns a scripted sequence of responses and records every create() call."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = self  # so client.messages.create(...) resolves here

    def create(self, **kwargs):
        # Snapshot the messages list — the loop mutates it in place, so we must
        # capture the sequence AT CALL TIME, not a live reference to the final state.
        rec = dict(kwargs)
        rec["messages"] = list(kwargs.get("messages", []))
        self.calls.append(rec)
        return self.script.pop(0)


@pytest.fixture()
def df_path(tmp_path):
    p = tmp_path / "data.csv"
    pd.DataFrame({"g": ["a", "a", "b"], "v": [1, 2, 3]}).to_csv(p, index=False)
    return str(p)


def _events(frames):
    return [json.loads(f[len("data: ") :]) for f in frames]


def test_assistant_turn_appended_before_tool_result(df_path):
    client = FakeClient(
        [
            _Resp([tool_use("profile_data", {}, id="p0")]),
            _Resp([tool_use("finish", {"answer": "done", "findings": []}, id="f1")]),
        ]
    )
    frames = list(run_investigation("q", df_path, SSEEmitter("t"), client=client))

    # The 2nd model call's transcript must end: ..., assistant(tool_use), user(tool_result)
    msgs = client.calls[1]["messages"]
    assert [m["role"] for m in msgs[-2:]] == ["assistant", "user"]
    assert msgs[-1]["content"][0]["type"] == "tool_result"

    types = [e["type"] for e in _events(frames)]
    assert "report" in types and "done" in types


def test_error_feeds_back_as_is_error_and_retries(df_path):
    client = FakeClient(
        [
            _Resp([tool_use("profile_data", {}, id="p0")]),
            _Resp([tool_use("run_pandas", {"hypothesis": "h", "code": "df['nope']"}, id="r1")]),
            _Resp([tool_use("run_pandas", {"hypothesis": "h2", "code": "result = int(df['v'].sum())"}, id="r2")]),
            _Resp([tool_use("finish", {"answer": "a", "findings": []}, id="f1")]),
        ]
    )
    frames = list(run_investigation("q", df_path, SSEEmitter("t"), client=client))
    types = [e["type"] for e in _events(frames)]
    assert "error" in types  # the broken query surfaced
    assert "retry" in types  # and we signalled a self-correction

    # The tool_result handed back for the broken call must be is_error=True.
    tr = client.calls[2]["messages"][-1]["content"][0]
    assert tr["type"] == "tool_result" and tr["is_error"] is True
    assert "KeyError" in tr["content"]  # the verbatim traceback the model reads


def test_loop_cap_forces_finish(df_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_STEPS", 3)
    never_finish = _Resp([tool_use("run_pandas", {"hypothesis": "h", "code": "result = 1"}, id="r")])
    client = FakeClient(
        [_Resp([tool_use("profile_data", {}, id="p")])]
        + [never_finish for _ in range(5)]  # keeps looping, never calls finish
        + [_Resp([tool_use("finish", {"answer": "forced", "findings": []}, id="f")])]  # forced_finish call
    )
    events = _events(run_investigation("q", df_path, SSEEmitter("t"), client=client))
    assert any(e["type"] == "cap_hit" and e["reason"] == "max_steps" for e in events)
    assert any(e["type"] == "done" and e["stopped_reason"] == "max_steps" for e in events)


def test_grounding_flags_ungrounded_claim(df_path):
    client = FakeClient(
        [
            _Resp([tool_use("profile_data", {}, id="p")]),
            _Resp([tool_use("run_pandas", {"hypothesis": "h", "code": "result = int(df['v'].sum())"}, id="r")]),
            _Resp(
                [
                    tool_use(
                        "finish",
                        {
                            "answer": "a",
                            "findings": [
                                {"claim": "grounded", "evidence_step": 1},
                                {"claim": "bogus", "evidence_step": 99},
                            ],
                        },
                        id="f",
                    )
                ]
            ),
        ]
    )
    events = _events(run_investigation("q", df_path, SSEEmitter("t"), client=client))
    report = next(e for e in events if e["type"] == "report")
    grounded = {f["evidence_step"]: f["grounded"] for f in report["findings"]}
    assert grounded[1] is True  # step 1 produced a real result
    assert grounded[99] is False  # no such step -> flagged
