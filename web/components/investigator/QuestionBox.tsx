"use client";

import { type ChangeEvent, useRef, useState } from "react";

interface Props {
  running: boolean;
  backend: string;
  onRun: (question: string, datasetId?: string) => void;
  onStop: () => void;
  onReplay: () => void;
}

// Question input + dataset picker (bundled demo, or upload your own CSV) + run/stop
// + a "play recorded run" escape hatch. NOT a chat box — a single investigation kickoff.
export function QuestionBox({ running, backend, onRun, onStop, onReplay }: Props) {
  const [question, setQuestion] = useState("Why did signups drop in March?");
  const [datasetId, setDatasetId] = useState<string | undefined>(undefined); // undefined -> demo
  const [uploadName, setUploadName] = useState<string | null>(null);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadErr(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${backend}/upload`, { method: "POST", body: fd });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? res.statusText);
      }
      const { dataset_id } = (await res.json()) as { dataset_id: string };
      setDatasetId(dataset_id);
      setUploadName(file.name);
    } catch (err) {
      setUploadErr(String((err as Error).message ?? err));
      setUploadName(null);
      setDatasetId(undefined);
    } finally {
      e.target.value = "";
    }
  }

  return (
    <div className="question-box">
      <label className="qb-label" htmlFor="qb-input">
        Ask a question about a dataset
      </label>
      <div className="qb-row">
        <input
          id="qb-input"
          className="qb-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. why did signups drop in March?"
          disabled={running}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !running && question.trim()) onRun(question, datasetId);
          }}
        />
        {running ? (
          <button className="btn btn-stop" onClick={onStop}>
            Stop
          </button>
        ) : (
          <button className="btn btn-run" disabled={!question.trim()} onClick={() => onRun(question, datasetId)}>
            Investigate
          </button>
        )}
      </div>

      <div className="qb-meta">
        <span className="qb-dataset">
          Dataset: <b>{datasetId ? uploadName : "demo — signups.csv"}</b>
        </span>
        <button className="linklike" onClick={() => fileRef.current?.click()} disabled={running}>
          upload a CSV
        </button>
        {datasetId && (
          <button
            className="linklike"
            onClick={() => {
              setDatasetId(undefined);
              setUploadName(null);
            }}
            disabled={running}
          >
            use demo
          </button>
        )}
        <span className="qb-spacer" />
        <button className="linklike" onClick={onReplay} disabled={running}>
          ▶ play recorded run
        </button>
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onFile} />
      </div>

      {uploadErr && <div className="qb-err">Upload failed: {uploadErr}</div>}
    </div>
  );
}
