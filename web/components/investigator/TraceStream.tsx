import type { ViewState } from "@/lib/investigator/reducer";

import { StepCard } from "./StepCard";

// The rail of step-units. A left connector spine (drawn in CSS on each card's
// rail) links the steps into a single vertical chain.
export function TraceStream({ state }: { state: ViewState }) {
  if (state.steps.length === 0) return null;
  return (
    <div className="trace-stream">
      {state.steps.map((s) => (
        <StepCard key={s.step} step={s} />
      ))}
      {state.capHit && <div className="cap-note">Hit its budget ({state.capHit}) — wrapping up from what it had.</div>}
    </div>
  );
}
