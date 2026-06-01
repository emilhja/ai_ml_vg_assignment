import { useCallback, useEffect, useRef, useState } from "react";
import type { EventItem } from "../api";

export function useSessionStream(sessionId: string | null) {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [statusline, setStatusline] = useState<string | null>(null);
  const cursorRef = useRef(-1);
  const sourceRef = useRef<EventSource | null>(null);

  const mergeEvents = useCallback((incoming: EventItem[]) => {
    if (!incoming.length) return;
    setEvents((prev) => {
      const map = new Map(prev.map((e) => [e.event_idx, e]));
      for (const item of incoming) map.set(item.event_idx, item);
      return [...map.values()].sort((a, b) => a.event_idx - b.event_idx);
    });
    cursorRef.current = Math.max(cursorRef.current, ...incoming.map((e) => e.event_idx));
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setEvents([]);
      setConnected(false);
      return;
    }
    cursorRef.current = -1;
    setEvents([]);
    const url = `/api/v1/sessions/${sessionId}/stream?from_event_idx=-1`;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);

    source.addEventListener("events", (ev) => {
      const data = JSON.parse((ev as MessageEvent).data) as { items: EventItem[] };
      mergeEvents(data.items ?? []);
    });
    source.addEventListener("statusline", (ev) => {
      const data = JSON.parse((ev as MessageEvent).data) as { text?: string };
      if (data.text) setStatusline(data.text);
    });
    source.addEventListener("heartbeat", () => setConnected(true));

    return () => {
      source.close();
      sourceRef.current = null;
      setConnected(false);
    };
  }, [sessionId, mergeEvents]);

  return { events, connected, statusline };
}
