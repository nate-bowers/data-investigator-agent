"use client";

import { type ChangeEvent, useRef, useState } from "react";

interface Props {
  running: boolean;
  backend: string;
  datasetId?: string;
  onDatasetChange: (id?: string) => void;
  onRun: (question: string, datasetId?: string) => void;
  onStop: () => void;
  onReplay: () => void;
}

// Question input + dataset picker (bundled demo or uploaded CSV) + run/stop
// + a "play recorded run" control. `datasetId` is owned by the page so the
// context panel can show the current dataset's schema.
export function QuestionBox({ running, backend, datasetId, onDatasetChange, onRun, onStop, onReplay }: Props) {
  const [question, setQuestion] = useState("Why did signups drop in March?");
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
      onDatasetChange(dataset_id);
      setUploadName(file.name);
    } catch (err) {
      setUploadErr(String((err as Error).message ?? err));
      setUploadName(null);
      onDatasetChange(undefined);
    } finally {
      e.target.value = "";
    }
  }

  return (
    <div className="question-box">
      <label className="qb-label" htmlFor="qb-input">
        Ask a question about the data
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
          Dataset: <b>{datasetId ? uploadName : "demo (signups.csv)"}</b>
        </span>
        <button className="linklike" onClick={() => fileRef.current?.click()} disabled={running}>
          upload a CSV
        </button>
        {datasetId && (
          <button
            className="linklike"
            onClick={() => {
              onDatasetChange(undefined);
              setUploadName(null);
            }}
            disabled={running}
          >
            use demo
          </button>
        )}
        <span className="qb-spacer" />
        <button className="linklike" onClick={onReplay} disabled={running}>
          <span aria-hidden="true">▶ </span>play recorded run
        </button>
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onFile} />
      </div>

      <p className="qb-note">
        Uploaded CSVs run in an isolated sandbox and are auto-deleted within ~1 hour. Don&apos;t upload sensitive data.
      </p>

      {uploadErr && <div className="qb-err">Upload failed: {uploadErr}</div>}
    </div>
  );
}
