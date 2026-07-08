"use client";

import { useCallback, useEffect, useState } from "react";

import { ContextPanel } from "@/components/investigator/ContextPanel";
import { FinalReport } from "@/components/investigator/FinalReport";
import { LoopMeter } from "@/components/investigator/LoopMeter";
import { QuestionBox } from "@/components/investigator/QuestionBox";
import { TraceStream } from "@/components/investigator/TraceStream";
import { useAgentContext } from "@/lib/investigator/context";
import type { InvestigationEvent } from "@/lib/investigator/events";
import { useInvestigation } from "@/lib/investigator/useInvestigation";

import "./investigator.css";

const RECORDING_URL = "/recordings/signups-march-dip.json";

export default function InvestigatorPage() {
  const { state, startLive, replay, stop, backend } = useInvestigation();
  const [datasetId, setDatasetId] = useState<string | undefined>(undefined);
  const ctx = useAgentContext(datasetId);
  const [recording, setRecording] = useState<InvestigationEvent[] | null>(null);
  const [offerRecorded, setOfferRecorded] = useState(false);

  useEffect(() => {
    fetch(RECORDING_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then(setRecording)
      .catch(() => setRecording(null));
  }, []);

  const running = state.status === "running";

  const onRun = useCallback(
    (q: string, ds?: string) => {
      setOfferRecorded(false);
      void startLive(q, ds);
    },
    [startLive],
  );

  const onReplay = useCallback(() => {
    if (recording) replay(recording);
  }, [recording, replay]);

  useEffect(() => {
    if (state.status === "error" && state.source === "live") setOfferRecorded(true);
  }, [state.status, state.source]);

  return (
    <main className="investigator">
      <header className="hero">
        <h1>Data Investigator</h1>
        <p className="tagline">
          Watch an agent investigate a dataset — it writes and runs its own pandas, reads each result to decide the next
          move, fixes its own broken code, and stops when it has the answer.{" "}
          <b>The path isn&apos;t hardcoded — the data drives it.</b>
        </p>
      </header>

      <div className="layout">
        <ContextPanel ctx={ctx} />

        <div className="main-col">
          <QuestionBox
            running={running}
            backend={backend}
            datasetId={datasetId}
            onDatasetChange={setDatasetId}
            onRun={onRun}
            onStop={stop}
            onReplay={onReplay}
          />

          {offerRecorded && recording && (
            <div className="cold-note">
              Couldn&apos;t reach the backend{state.errorMessage ? ` (${state.errorMessage})` : ""}.{" "}
              <button className="linklike" onClick={onReplay}>
                ▶ play the recorded run instead
              </button>
            </div>
          )}

          <LoopMeter state={state} />
          <TraceStream state={state} />
          <FinalReport state={state} />

          {state.status === "idle" && (
            <p className="empty-hint">
              Hit <b>Investigate</b> to watch it work, or{" "}
              <button className="linklike" onClick={onReplay} disabled={!recording}>
                play the recorded run
              </button>
              . The agent&apos;s tools and the data it sees are on the left — the trace of its tool calls appears here.
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
