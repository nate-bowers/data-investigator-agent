// Mirrors agent/app/events.py, the SSE event contract. Keep the two in sync.

export type Phase = "orient" | "query";

export interface BaseEvent {
  type: string;
  run_id: string;
  seq: number;
  step: number;
  ts: number;
}

export interface RunStart extends BaseEvent { type: "run_start"; question: string; model: string; }
export interface StepStart extends BaseEvent { type: "step_start"; phase: Phase; }
export interface Hypothesis extends BaseEvent { type: "hypothesis"; text: string; }
export interface Code extends BaseEvent { type: "code"; code: string; attempt: number; }
export interface Result extends BaseEvent { type: "result"; kind: "profile" | "pandas"; result: string; attempt: number; }
export interface ErrorEvent extends BaseEvent { type: "error"; traceback: string; attempt: number; }
export interface Retry extends BaseEvent { type: "retry"; attempt: number; }
export interface RetryExhausted extends BaseEvent { type: "retry_exhausted"; }
export interface Decision extends BaseEvent { type: "decision"; thinking: string; stop_reason: string; }
export interface ChartEvent extends BaseEvent { type: "chart"; kind: string; reason: string; png: string; }
export interface CapHit extends BaseEvent { type: "cap_hit"; reason: string; }
export interface Finding { claim: string; evidence_step: number; grounded: boolean; }
export interface ReportEvent extends BaseEvent { type: "report"; answer: string; findings: Finding[]; }
export interface Done extends BaseEvent { type: "done"; stopped_reason: string; }
export interface Heartbeat extends BaseEvent { type: "heartbeat"; }

export type InvestigationEvent =
  | RunStart | StepStart | Hypothesis | Code | Result | ErrorEvent
  | Retry | RetryExhausted | Decision | ChartEvent | CapHit
  | ReportEvent | Done | Heartbeat;
