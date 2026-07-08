import type { ViewState } from "@/lib/investigator/reducer";
import { recoveredCount } from "@/lib/investigator/reducer";

// The at-a-glance legibility bar: phase, step count, self-corrections, and how it
// stopped — so someone can glance and see "10 steps, 1 self-corrected, self-stopped".
export function LoopMeter({ state }: { state: ViewState }) {
  if (state.status === "idle") return null;
  const recovered = recoveredCount(state);
  const last = state.steps[state.steps.length - 1];
  const phase = last?.phase === "orient" ? "orient" : `step ${last?.step ?? 0}`;

  const status =
    state.status === "done"
      ? state.stoppedReason === "finish"
        ? "self-stopped — answered"
        : `stopped: ${state.stoppedReason}`
      : state.status === "error"
        ? "connection error"
        : "investigating…";

  return (
    <div className="loop-meter">
      <span className={`pulse pulse-${state.status}`} />
      <span className="lm-phase">{phase}</span>
      <span className="lm-sep">·</span>
      <span>{state.steps.length} steps</span>
      {recovered > 0 && (
        <>
          <span className="lm-sep">·</span>
          <span className="lm-recover">{recovered} self-corrected</span>
        </>
      )}
      <span className="lm-sep">·</span>
      <span className="lm-status">{status}</span>
      {state.model && <span className="lm-model">{state.model}</span>}
      {state.source === "recorded" && <span className="lm-badge">recorded run</span>}
    </div>
  );
}
