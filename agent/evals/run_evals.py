"""Run the eval suite and report the three headline metrics.

Usage (from the agent/ directory, with the venv active and ANTHROPIC_API_KEY set):

  python -m evals.gen_data                 # build the datasets (once)
  python -m evals.run_evals --selftest     # validate the graders on the recorded run (NO API, free)
  python -m evals.run_evals --limit 3      # smoke test: 3 real investigations
  python -m evals.run_evals                # the full suite (spends API on your key)

Options: --case ID, --dataset NAME, --limit N, --workers N, --out PATH, --selftest.

Each live investigation is several Anthropic calls. The full suite is ~15 investigations
plus a few judge calls. Start with --selftest, then --limit 3, then the full run.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

from evals import harness
from evals.suite import build_suite

REC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..",
                                    "web", "public", "recordings", "signups-march-dip.json"))


def _result_from_events(case_id, events):
    run = harness.RunResult(case_id=case_id)
    run.events = events
    parts = []
    for ev in events:
        t = ev.get("type")
        if t == "result":
            parts.append(str(ev.get("result", "")))
        elif t == "report":
            run.answer, run.findings = ev.get("answer", ""), ev.get("findings", []) or []
        elif t == "done":
            run.done_reason = ev.get("stopped_reason", "")
    run.ledger_text = "\n".join(parts)
    return run


def selftest():
    """Prove the grounding + self-correction graders work on the committed recorded run."""
    events = json.load(open(REC))
    run = _result_from_events("recorded-signups-march", events)
    g = harness.grade_grounding(run)
    s = harness.grade_selfcorrect(run)
    print(f"Recorded run: {len(events)} events, {len(run.findings)} findings, done={run.done_reason!r}")
    print(f"GROUNDING     report_numbers={g['report_numbers']} direct={g['direct']} "
          f"derived={g['derived']} unexplained={g['ungrounded']} bad_evidence_steps={g['bad_evidence_steps']}")
    print(f"SELF-CORRECT  errors={s['errors']} recovered={s['recovered']} exhausted={s['exhausted']} "
          f"rate={s['recovery_rate']}")
    print("\nGraders run with no API. Use --limit 3 next for a live smoke test.")


def run_one(case, judge_client):
    run = harness.run_case(case)  # client=None -> its own Anthropic client (thread-safe)
    acc = harness.grade_accuracy(case, run, judge_client)
    gnd = harness.grade_grounding(run)
    sc = harness.grade_selfcorrect(run)
    print(f"  {'OK ' if acc['correct'] else 'XX '}{case.id:14s} {case.kind:11s} "
          f"acc={acc['correct']} ground_ungrounded={len(gnd.get('ungrounded', []))} "
          f"errs={sc['errors']} recov={sc['recovered']}"
          + (f"  ERROR: {run.error}" if run.error else ""))
    return {"case_id": case.id, "kind": case.kind, "dataset": case.dataset_label,
            "question": case.question, "reference": case.reference, "answer": run.answer,
            "accuracy": acc, "grounding": gnd, "selfcorrect": sc, "run_error": run.error,
            "ledger_text": run.ledger_text}


def summarize(rows):
    acc_total = sum(1 for r in rows if r["accuracy"]["correct"])
    numeric = [r for r in rows if r["kind"] in ("numeric", "categorical")]
    causal = [r for r in rows if r["kind"] == "causal"]
    rep_nums = sum(r["grounding"].get("report_numbers", 0) for r in rows)
    derived = sum(len(r["grounding"].get("derived", [])) for r in rows)
    ungrounded = sum(len(r["grounding"].get("ungrounded", [])) for r in rows)
    errs = sum(r["selfcorrect"]["errors"] for r in rows)
    recov = sum(r["selfcorrect"]["recovered"] for r in rows)
    n = len(rows)
    print("\n" + "=" * 68)
    print(f"ACCURACY       {acc_total}/{n} correct  "
          f"(exact {sum(1 for r in numeric if r['accuracy']['correct'])}/{len(numeric)}, "
          f"judge {sum(1 for r in causal if r['accuracy']['correct'])}/{len(causal)})")
    print(f"GROUNDING      {rep_nums - ungrounded}/{rep_nums} numbers in reports trace to a computed "
          f"result  ({ungrounded} unexplained; {derived} were the agent's shown-work arithmetic)")
    if errs:
        print(f"SELF-CORRECT   {recov}/{errs} failed queries recovered within 3 retries "
              f"({recov / errs:.0%})")
    else:
        print("SELF-CORRECT   no query errors occurred in this run")
    print("=" * 68)
    print("\nSuggested bullet numbers (verify against results.json before using):")
    print(f"  - Answers {acc_total}/{n} held-out questions correctly, graded against known results.")
    print(f"  - {ungrounded} unexplained numbers across {n} runs; every figure traces to a computed "
          f"result, directly or as the agent's own arithmetic on grounded values.")
    if errs:
        print(f"  - Recovers from {recov / errs:.0%} of failed queries within 3 retries by reading the "
              f"traceback and rewriting.")
    return {"n": n, "accuracy_correct": acc_total, "grounding_report_numbers": rep_nums,
            "grounding_ungrounded": ungrounded, "grounding_derived": derived,
            "selfcorrect_errors": errs, "selfcorrect_recovered": recov}


def write_history(rows, summ, stamp):
    """Append a dated summary to evals/history and save the raw rows for that run."""
    hist_dir = os.path.join(os.path.dirname(__file__), "history")
    os.makedirs(hist_dir, exist_ok=True)
    with open(os.path.join(hist_dir, f"{stamp}.json"), "w") as f:
        json.dump(rows, f, indent=2, default=str)
    n, errs, recov = summ["n"], summ["selfcorrect_errors"], summ["selfcorrect_recovered"]
    grounded = summ["grounding_report_numbers"] - summ["grounding_ungrounded"]
    block = (
        f"## {stamp}  (model {harness.config.MODEL})\n\n"
        f"- Accuracy: {summ['accuracy_correct']}/{n} correct\n"
        f"- Grounding: {grounded}/{summ['grounding_report_numbers']} numbers traceable "
        f"({summ['grounding_ungrounded']} unexplained, {summ.get('grounding_derived', 0)} shown-work arithmetic)\n"
        f"- Self-correction: {recov}/{errs} failed queries recovered"
        + (f" ({recov / errs:.0%})" if errs else " (no errors)") + "\n\n"
    )
    idx = os.path.join(hist_dir, "HISTORY.md")
    need_header = (not os.path.exists(idx)) or os.path.getsize(idx) == 0
    with open(idx, "a") as f:
        if need_header:
            f.write("# Eval run history\n\n")
        f.write(block)
    print(f"History written to history/{stamp}.json and history/HISTORY.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--case")
    ap.add_argument("--dataset")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--history", action="store_true", help="append a dated summary to evals/history")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results.json"))
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    cases = build_suite()
    if args.case:
        cases = [c for c in cases if c.id == args.case]
    if args.dataset:
        cases = [c for c in cases if c.dataset_label == args.dataset]
    if args.limit:
        cases = cases[: args.limit]

    print(f"Running {len(cases)} live investigations against the Anthropic API "
          f"(model {harness.config.MODEL}). This spends tokens on your key.\n")
    import anthropic

    judge = anthropic.Anthropic(timeout=60.0, max_retries=2)
    if args.workers > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            rows = list(ex.map(lambda c: run_one(c, judge), cases))
    else:
        rows = [run_one(c, judge) for c in cases]

    with open(args.out, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    summ = summarize(rows)
    if args.history:
        from datetime import datetime

        write_history(rows, summ, datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    print(f"\nPer-case detail written to {args.out}")


if __name__ == "__main__":
    main()
