import type { AgentContext } from "@/lib/investigator/context";

// Renders the agent's inputs: the tools it can call and the dataset schema it
// operates on.
export function ContextPanel({ ctx }: { ctx: AgentContext }) {
  return (
    <aside className="context-panel">
      <section className="cp-section">
        <h3 className="cp-title">Tools the agent can call</h3>
        <ul className="cp-tools">
          {ctx.tools.map((t) => (
            <li key={t.name}>
              <code>{t.name}</code>
              <span>{t.description}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="cp-section">
        <h3 className="cp-title">The data it&apos;s looking at</h3>
        {ctx.dataset ? (
          <>
            <p className="cp-ds">
              <b>{ctx.dataset.name}</b> · {ctx.dataset.rows.toLocaleString()} rows · {ctx.dataset.columns.length} columns
            </p>
            <ul className="cp-cols">
              {ctx.dataset.columns.map((c) => (
                <li key={c}>
                  <code>{c}</code>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="cp-muted">no dataset loaded</p>
        )}
      </section>
    </aside>
  );
}
