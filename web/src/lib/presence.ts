"use client";

import { useEffect, useRef, useState } from "react";

export interface Viewer {
  viewer_id: string;
  name: string;
}

type Handler = (msg: Record<string, unknown>) => void;

/** Live presence over the cockpit WebSocket (docs/28 §5). Degrades silently to
 *  "just me" if the socket can't connect. `onEvent` fires for non-presence
 *  messages (e.g. exception_resolved) so the cockpit can refresh in place. */
export function usePresence(runId: string, onEvent?: Handler) {
  const [viewers, setViewers] = useState<Viewer[]>([]);
  const [connected, setConnected] = useState(false);
  const cb = useRef(onEvent);
  cb.current = onEvent;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/api/v1/runs/${runId}/ws`;
    let ws: WebSocket | null = null;
    let keepalive: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    try {
      ws = new WebSocket(url);
    } catch {
      return;
    }
    ws.onopen = () => {
      setConnected(true);
      keepalive = setInterval(
        () => ws?.readyState === 1 && ws.send("ping"),
        25_000,
      );
    };
    ws.onmessage = (e) => {
      let m: Record<string, unknown>;
      try {
        m = JSON.parse(e.data);
      } catch {
        return;
      }
      if (m.type === "presence" && Array.isArray(m.viewers))
        setViewers(m.viewers as Viewer[]);
      else if (m.type !== "hello") cb.current?.(m);
    };
    ws.onclose = () => {
      if (!closed) setConnected(false);
    };
    ws.onerror = () => setConnected(false);

    return () => {
      closed = true;
      if (keepalive) clearInterval(keepalive);
      ws?.close();
    };
  }, [runId]);

  return { viewers, connected };
}
