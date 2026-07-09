import type { ReactNode } from "react";

import type { ViewState } from "@/lib/investigator/reducer";

// Minimal inline markdown for the model's answer (**bold**, `code`) — no dep.
function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) nodes.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else nodes.push(<code key={k++}>{tok.slice(1, -1)}</code>);
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

// The grounded final report: the answer, then each claim linked to the step whose
// result supports it (✓ grounded / ⚠ ungrounded).
export function FinalReport({ state }: { state: ViewState }) {
  if (!state.report) return null;
  const { answer, findings } = state.report;
  return (
    <section className="final-report">
      <h2>Answer</h2>
      <p className="report-answer">{inline(answer)}</p>

      {findings.length > 0 && (
        <ul className="findings">
          {findings.map((f, i) => (
            <li key={i} className={f.grounded ? "grounded" : "ungrounded"}>
              <span className="finding-mark" aria-hidden="true">
                {f.grounded ? "✓" : "⚠"}
              </span>
              <span className="visually-hidden">{f.grounded ? "Grounded: " : "Ungrounded: "}</span>
              <span className="finding-claim">{f.claim}</span>
              <span className="finding-step">step {f.evidence_step}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="report-foot">
        {state.stoppedReason === "finish"
          ? "The agent stopped on its own once it had a grounded answer."
          : `Stopped by the ${state.stoppedReason} guard.`}{" "}
        Every claim links to the step whose result supports it.
      </p>
    </section>
  );
}
