"use client";

import { useCallback, useReducer, useRef } from "react";

import type { InvestigationEvent } from "./events";
import { initialState, reduce } from "./reducer";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/**
 * Drives the investigation viewer. Two sources feed one reducer:
 *  - startLive():  POST /investigate and read the text/event-stream with a fetch
 *                  streaming reader (carries the POST body, unlike EventSource).
 *  - replay():     dispatch a recorded event array on a timer, rendered through the
 *                  same reducer as the live stream.
 */
export function useInvestigation() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startLive = useCallback(
    async (question: string, datasetId?: string) => {
      stop();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: "__start__", source: "live", question });
      try {
        const res = await fetch(`${BACKEND}/investigate`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question, dataset_id: datasetId ?? null }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) {
          // Surface the backend's reason (e.g. the rate-limit message) if present.
          let msg = `backend responded ${res.status}`;
          try {
            const j = (await res.json()) as { detail?: string };
            if (j?.detail) msg = j.detail;
          } catch {
            /* non-JSON error body — keep the status message */
          }
          throw new Error(msg);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buf.indexOf("\n\n")) >= 0) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const line = frame.split("\n").find((l) => l.startsWith("data: "));
            if (line) dispatch(JSON.parse(line.slice(6)) as InvestigationEvent);
          }
        }
      } catch (e) {
        const err = e as { name?: string; message?: string };
        if (err?.name !== "AbortError") {
          dispatch({ type: "__error__", message: String(err?.message ?? e) });
        }
      } finally {
        abortRef.current = null;
      }
    },
    [stop],
  );

  const replay = useCallback(
    (events: InvestigationEvent[]) => {
      stop();
      dispatch({ type: "__start__", source: "recorded" });
      let i = 0;
      const tick = () => {
        if (i >= events.length) return;
        const ev = events[i++];
        dispatch(ev);
        // Stagger delays by event type so results, charts, and the report get longer holds.
        const delay =
          ev.type === "chart" ? 380 : ev.type === "result" || ev.type === "error" || ev.type === "report" ? 320 : 170;
        timerRef.current = setTimeout(tick, delay);
      };
      tick();
    },
    [stop],
  );

  return { state, startLive, replay, stop, backend: BACKEND };
}
