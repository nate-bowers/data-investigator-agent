# Evals

A small offline eval harness that measures the agent on three axes over a fixed
question set with known answers.

- **Accuracy**: does it reach the right answer? Exact-match for numeric and
  categorical questions, an LLM judge for causal ones.
- **Grounding**: does it avoid hallucinating? Every number in the final report must
  match a value the agent actually computed (the ledger of `result` events).
- **Self-correction**: does it recover? Of the `run_pandas` calls that raised, how
  many were followed by a passing query before the 3-retry cap.

## Suite

15 questions over 4 datasets: the planted-story `signups` demo plus three generated
datasets (`sales`, `support_tickets`, `tips`) with fixed seeds. Numeric and categorical
reference answers are computed from the CSVs in `suite.py`, so they cannot drift.
Causal reference answers are written by hand. Three questions sit on datasets with a
non-numeric value in a numeric column, which forces a traceback and a self-correction.

## Run

From the `agent/` directory, with the venv active and `ANTHROPIC_API_KEY` set:

```bash
python -m evals.gen_data              # build the datasets (once)
python -m evals.run_evals --selftest  # validate the graders on the recorded run (no API)
python -m evals.run_evals --limit 3   # live smoke test: 3 investigations
python -m evals.run_evals             # full suite, writes results.json + prints a summary
```

Each live investigation is several Anthropic calls, so the full run spends tokens on
your key. Start with `--selftest`, then `--limit 3`, then the full run.

## Files

```
gen_data.py    generate the deterministic datasets
suite.py       the question set + reference answers
harness.py     the runner (drives the agent, parses events) + the three graders
run_evals.py   CLI: run + grade + summarize
```
