# Eval run history

15-question suite over 4 datasets. Accuracy is exact-match (numeric/categorical) plus an
LLM judge (causal). Grounding checks that every number in a report traces to a value the
agent computed. Self-correction is the share of failed run_pandas calls recovered within
the 3-retry cap. Counts vary run to run because the agent's exact path is not fixed.

Note: between the two runs below the grounding checker was refined to credit numbers the
agent derived by simple arithmetic from computed values (a stated difference or percentage),
which is why run 1 lists them as "ungrounded" and run 2 as "shown-work arithmetic". Neither
run had a hallucinated figure.

## 2026-07-09_150233  (model claude-sonnet-4-6)

- Accuracy: 15/15 correct
- Grounding: 129/141 numbers grounded (12 ungrounded)
- Self-correction: 4/4 failed queries recovered (100%)

## 2026-07-09_150848  (model claude-sonnet-4-6)

- Accuracy: 15/15 correct
- Grounding: 132/132 numbers traceable (0 unexplained, 12 shown-work arithmetic)
- Self-correction: 3/3 failed queries recovered (100%)

