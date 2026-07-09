"use client";

import { useEffect, useState } from "react";

// The agent's input context: the tools it can call plus the dataset schema. Fetched
// from the backend's /context so the panel reflects the current agent config (and
// updates for uploaded CSVs); a fallback keeps it populated when the backend is cold.

export interface AgentContext {
  tools: { name: string; description: string }[];
  dataset: { name: string; columns: string[]; rows: number } | null;
}

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export const FALLBACK: AgentContext = {
  tools: [
    { name: "profile_data", description: "Profile the dataset: shape, columns, dtypes, nulls, sample rows." },
    { name: "run_pandas", description: "Run a pandas snippet to test one hypothesis; optionally chart the finding." },
    { name: "finish", description: "Declare the question answered, each claim tied to the step that supports it." },
  ],
  dataset: {
    name: "signups.csv",
    columns: ["signup_date", "user_id", "channel", "campaign_id", "country", "device", "activated"],
    rows: 2224,
  },
};

export function useAgentContext(datasetId?: string): AgentContext {
  const [ctx, setCtx] = useState<AgentContext | null>(null);
  useEffect(() => {
    const url = new URL(`${BACKEND}/context`);
    if (datasetId) url.searchParams.set("dataset_id", datasetId);
    let live = true;
    fetch(url.toString())
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (live && d) setCtx(d as AgentContext);
      })
      .catch(() => {
        /* cold backend: fall back below */
      });
    return () => {
      live = false;
    };
  }, [datasetId]);
  return ctx ?? FALLBACK;
}
