"use client";

import { useEffect, useState } from "react";

// The only public config the frontend needs. No secrets ever cross this line.
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export default function InvestigatorPage() {
  const [health, setHealth] = useState("checking…");

  // Block-0 smoke: confirm the browser can reach the backend cross-origin.
  useEffect(() => {
    fetch(`${BACKEND}/health`)
      .then((r) => r.json())
      .then((d) => setHealth(`ok — model ${d.model}`))
      .catch((e) => setHealth(`unreachable (${String(e)})`));
  }, []);

  return (
    <main style={{ padding: 32, maxWidth: 720 }}>
      <h1>Data Investigator</h1>
      <p>
        Backend: <code>{BACKEND}</code>
      </p>
      <p>Health: {health}</p>
      <p style={{ color: "#888" }}>
        Block 0 scaffold — the streaming investigation viewer arrives in Block 7.
      </p>
    </main>
  );
}
