import type { StepState } from "@/lib/investigator/reducer";

// Renders one reasoning step as a tool call: the tool, its input, and what it
// returned. An errored step turns amber and shows the self-correction badge; the
// fix lands in a following card.
export function StepCard({ step }: { step: StepState }) {
  const errored = step.status === "error";
  const isOrient = step.phase === "orient";
  const tool = isOrient ? "profile_data" : "run_pandas";

  return (
    <article className={`step-card${errored ? " step-error" : ""}`}>
      <div className="step-rail">
        <div className={`step-chip${errored ? " chip-error" : ""}${isOrient ? " chip-orient" : ""}`}>
          {isOrient ? <span aria-hidden="true">◎</span> : step.step}
        </div>
      </div>

      <div className="step-body">
        <div className="step-head">
          <span className="tool-call">
            calls <code>{tool}</code>
          </span>
          <span className="phase-tag">{isOrient ? "orient" : `step ${step.step}`}</span>
          {errored && <span className="badge badge-error">query failed</span>}
          {step.retry && <span className="badge badge-recover">self-correcting →</span>}
          {step.retryExhausted && <span className="badge badge-error">gave up, pivoting</span>}
        </div>

        {step.thinking && <p className="thinking">{step.thinking}</p>}
        {step.hypothesis && <p className="hypothesis">{step.hypothesis}</p>}

        {step.code && (
          <div className="io">
            <span className="io-label">input</span>
            <pre className="code">
              <code>{step.code.trim()}</code>
            </pre>
          </div>
        )}

        {(step.error || step.result || step.status === "running") && (
          <div className="io">
            <span className="io-label">returned</span>
            {step.error ? (
              <pre className="result result-error">{step.error.trim()}</pre>
            ) : step.result ? (
              <pre className="result">{step.result.trim()}</pre>
            ) : (
              <div className="running-dots" aria-label="working">
                <span />
                <span />
                <span />
              </div>
            )}
          </div>
        )}

        {step.chart && (
          <figure className="chart">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/png;base64,${step.chart.png}`} alt={step.chart.reason} />
            <figcaption>
              Chose <b>{step.chart.kind}</b>: {step.chart.reason}
            </figcaption>
          </figure>
        )}
      </div>
    </article>
  );
}
