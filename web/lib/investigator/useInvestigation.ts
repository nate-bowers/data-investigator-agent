"use client";

import { useCallback, useReducer, useRef, useState } from "react";

import type { InvestigationEvent } from "./events";
import { initialState, reduce } from "./reducer";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

// If the first SSE byte hasn't arrived by this point, the free backend is almost
// certainly cold-starting, so surface the "waking" banner (without aborting the request).
const FIRST_BYTE_WATCHDOG_MS = 4500;

/**
 * Drives the investigation viewer. Two sources feed one reducer:
 *  - startLive():  POST /investigate and read the text/event-stream with a fetch
 *                  streaming reader (carries the POST body, unlike EventSource).
 *  - replay():     dispatch a recorded event array on a timer, rendered through the
 *                  same reducer as the live stream.
 */
export function useInvestigation() {
  const [state, dispatch] = useReducer(reduce, initialState);
  const [waking, setWaking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
    setWaking(false);
  }, []);

  // Fire-and-forget ping to start warming the (free-tier, cold-starting) backend.
  const warm = useCallback(() => {
    fetch(`${BACKEND}/health`).catch(() => {});
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    clearWatchdog();
  }, [clearWatchdog]);

  const startLive = useCallback(
    async (question: string, datasetId?: string) => {
      stop();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      dispatch({ type: "__start__", source: "live", question });
      // First-byte watchdog: if nothing streams within the window, the free backend
      // is likely waking up, so flag it so the page can offer the recorded run.
      // We deliberately do NOT abort the real request for slowness.
      setWaking(false);
      watchdogRef.current = setTimeout(() => setWaking(true), FIRST_BYTE_WATCHDOG_MS);
      try {
        const res = await fetch(`${BACKEND}/investigate`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ question, dataset_id: datasetId ?? null }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) {
          clearWatchdog();
          // Surface the backend's reason (e.g. the rate-limit message) if present.
          let msg = `backend responded ${res.status}`;
          try {
            const j = (await res.json()) as { detail?: string };
            if (j?.detail) msg = j.detail;
          } catch {
            /* non-JSON error body, keep the status message */
          }
          // A 429 means the backend is reachable and enforcing a rate limit, so
          // report it as a rate_limit case rather than a transport failure.
          dispatch({
            type: "__error__",
            message: msg,
            kind: res.status === 429 ? "rate_limit" : "transport",
            status: res.status,
          });
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          // First bytes are streaming, so the backend is awake; drop the "waking" flag.
          clearWatchdog();
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
          // A thrown error here is a real network/connection failure, so use the transport kind.
          dispatch({ type: "__error__", message: String(err?.message ?? e), kind: "transport" });
        }
      } finally {
        clearWatchdog();
        abortRef.current = null;
      }
    },
    [stop, clearWatchdog],
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

  return { state, startLive, replay, stop, warm, waking, backend: BACKEND };
}
