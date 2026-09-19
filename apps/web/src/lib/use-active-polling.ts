"use client";

import { useEffect, useRef } from "react";

type Poll = (signal: AbortSignal) => Promise<boolean>;

export function useActivePolling(
  active: boolean,
  poll: Poll,
  initialDelayMs = 2000,
  maximumDelayMs = 15000,
) {
  const pollRef = useRef(poll);
  pollRef.current = poll;

  useEffect(() => {
    if (!active) return;

    let stopped = false;
    let delay = initialDelayMs;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const clearTimer = () => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };

    const schedule = (wait: number) => {
      clearTimer();
      if (!stopped && !document.hidden) timer = setTimeout(() => void run(), wait);
    };

    const run = async () => {
      if (stopped || document.hidden || controller) return;
      const current = new AbortController();
      controller = current;
      let succeeded = false;
      try {
        succeeded = await pollRef.current(current.signal);
      } catch {
        succeeded = false;
      } finally {
        if (controller === current) controller = null;
      }

      if (stopped || document.hidden) return;
      if (current.signal.aborted) {
        delay = initialDelayMs;
        schedule(delay);
        return;
      }

      delay = Math.min(
        succeeded ? delay * 2 : Math.max(delay * 2, initialDelayMs),
        maximumDelayMs,
      );
      schedule(delay);
    };

    const onVisibilityChange = () => {
      clearTimer();
      if (document.hidden) {
        controller?.abort();
        return;
      }

      delay = initialDelayMs;
      if (!controller) void run();
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    if (!document.hidden) schedule(initialDelayMs);

    return () => {
      stopped = true;
      clearTimer();
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [active, initialDelayMs, maximumDelayMs]);
}
