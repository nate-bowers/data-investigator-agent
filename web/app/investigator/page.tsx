"use client";

import { useCallback, useEffect, useState } from "react";

import { FinalReport } from "@/components/investigator/FinalReport";
import { LoopMeter } from "@/components/investigator/LoopMeter";
import { QuestionBox } from "@/components/investigator/QuestionBox";
import { TraceStream } from "@/components/investigator/TraceStream";
import type { InvestigationEvent } from "@/lib/investigator/events";
import { useInvestigation } from "@/lib/investigator/useInvestigation";

import "./investigator.css";

const RECORDING_URL = "/recordings/signups-march-dip.json";

export default function InvestigatorPage() {
  const { state, startLive, replay, stop, backend } = useInvestigation();
  const [recording, setRecording] = useState<InvestigationEvent[] | null>(null);
  const [offerRecorded, setOfferRecorded] = useState(false);

  // Preload the committed recording so the demo-insurance replay is instant.
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

  // If a live run couldn't reach the backend (cold box), offer the recording.
  useEffect(() => {
    if (state.status === "error" && state.source === "live") setOfferRecorded(true);
  }, [state.status, state.source]);

  return (
    <main className="investigator">
      <header className="hero">
        <h1>Data Investigator</h1>
        <p className="tagline">
          Give it a question and a dataset. Watch it hypothesize, write and run its own pandas, read each result to
          decide the next move, fix its own broken code, and stop when it has the answer.{" "}
          <b>The path isn&apos;t hardcoded — the data drives it.</b>
        </p>
      </header>

      <QuestionBox running={running} backend={backend} onRun={onRun} onStop={stop} onReplay={onReplay} />

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
          Try the demo question above, or upload your own CSV. Not sure the backend&apos;s awake? Hit{" "}
          <button className="linklike" onClick={onReplay} disabled={!recording}>
            play recorded run
          </button>
          .
        </p>
      )}
    </main>
  );
}
