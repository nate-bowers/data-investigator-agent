// The single rendering path for both live and recorded runs: fold the SSE event
// stream into ordered StepCards + a final report. Pure and unit-testable; keeping
// all display semantics here keeps live and replay in sync.

import type { Finding, InvestigationEvent, Phase } from "./events";

export interface StepState {
  step: number;
  phase: Phase;
  thinking?: string;
  stopReason?: string;
  hypothesis?: string;
  code?: string;
  result?: string;
  resultKind?: "profile" | "pandas";
  error?: string; // traceback if this step's query errored
  retry?: boolean; // a self-correction was signalled
  retryExhausted?: boolean;
  chart?: { kind: string; reason: string; png: string };
  status: "running" | "ok" | "error";
}

export interface ViewState {
  runId?: string;
  question?: string;
  model?: string;
  steps: StepState[];
  report?: { answer: string; findings: Finding[] };
  status: "idle" | "running" | "done" | "error";
  stoppedReason?: string;
  capHit?: string;
  errorMessage?: string;
  errorKind?: "transport" | "rate_limit"; // distinguishes a 429 from a real connection failure
  errorStatus?: number; // HTTP status when the backend responded !ok
  source: "live" | "recorded" | null;
}

export type Action =
  | InvestigationEvent
  | { type: "__start__"; source: "live" | "recorded"; question?: string }
  | { type: "__error__"; message: string; kind?: "transport" | "rate_limit"; status?: number }
  | { type: "__reset__" };

export const initialState: ViewState = { steps: [], status: "idle", source: null };

function ensureStep(steps: StepState[], step: number, phase: Phase = "query"): StepState {
  let s = steps.find((x) => x.step === step);
  if (!s) {
    s = { step, phase, status: "running" };
    steps.push(s);
    steps.sort((a, b) => a.step - b.step);
  }
  return s;
}

export function reduce(state: ViewState, action: Action): ViewState {
  switch (action.type) {
    case "__reset__":
      return { ...initialState };
    case "__start__":
      return { ...initialState, status: "running", source: action.source, question: action.question };
    case "__error__":
      return {
        ...state,
        status: "error",
        errorMessage: action.message,
        errorKind: action.kind ?? "transport",
        errorStatus: action.status,
      };
    default:
      break;
  }

  const ev = action as InvestigationEvent;
  const steps = state.steps.map((s) => ({ ...s })); // fresh clones -> immutable vs prev state
  const next: ViewState = { ...state, steps };

  switch (ev.type) {
    case "run_start":
      return { ...initialState, runId: ev.run_id, question: ev.question, model: ev.model, status: "running", source: state.source };
    case "step_start":
      ensureStep(steps, ev.step, ev.phase).phase = ev.phase;
      return next;
    case "decision": {
      const s = ensureStep(steps, ev.step);
      s.thinking = ev.thinking;
      s.stopReason = ev.stop_reason;
      return next;
    }
    case "hypothesis":
      ensureStep(steps, ev.step).hypothesis = ev.text;
      return next;
    case "code":
      ensureStep(steps, ev.step).code = ev.code;
      return next;
    case "result": {
      const s = ensureStep(steps, ev.step);
      s.result = ev.result;
      s.resultKind = ev.kind;
      s.status = "ok";
      return next;
    }
    case "error": {
      const s = ensureStep(steps, ev.step);
      s.error = ev.traceback;
      s.status = "error";
      return next;
    }
    case "retry":
      ensureStep(steps, ev.step).retry = true;
      return next;
    case "retry_exhausted":
      ensureStep(steps, ev.step).retryExhausted = true;
      return next;
    case "chart":
      ensureStep(steps, ev.step).chart = { kind: ev.kind, reason: ev.reason, png: ev.png };
      return next;
    case "cap_hit":
      return { ...next, capHit: ev.reason };
    case "report":
      return { ...next, report: { answer: ev.answer, findings: ev.findings } };
    case "done":
      return { ...next, status: "done", stoppedReason: ev.stopped_reason };
    default:
      return state; // heartbeat, unknown
  }
}

// Derived: how many steps errored (and the run continued past them) — the
// "self-corrected" count the LoopMeter shows.
export function recoveredCount(state: ViewState): number {
  return state.steps.filter((s) => s.error).length;
}
