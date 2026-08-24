import { useCallback, useEffect, useRef, useState } from "react";

import { getResearchRun, isAbortError, startResearch } from "../api";
import type { ApiError, ResearchRun } from "../types";

const terminalStatuses = new Set<ResearchRun["status"]>(["completed", "partial", "blocked", "failed"]);

interface UseResearchRunOptions {
  onAuthenticationRequired?: () => void;
  pollIntervalMs?: number;
}

function asApiError(reason: unknown): ApiError {
  return typeof reason === "object" && reason !== null && "code" in reason && "message" in reason
    ? reason as ApiError
    : { code: "network_error", message: "无法更新研究任务状态。" };
}

export function useResearchRun(sourceId: number | null, options: UseResearchRunOptions = {}) {
  const onAuthenticationRequired = options.onAuthenticationRequired;
  const pollIntervalMs = options.pollIntervalMs ?? 1_000;
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const startControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setRun((current) => current?.source_id === sourceId ? current : null);
    setError(null);
  }, [sourceId]);

  useEffect(() => () => startControllerRef.current?.abort(), []);

  useEffect(() => {
    if (sourceId === null || run === null || run.source_id !== sourceId || terminalStatuses.has(run.status)) {
      return undefined;
    }
    const controller = new AbortController();
    let timer: number | undefined;
    let disposed = false;
    const poll = async () => {
      try {
        const next = await getResearchRun(run.id, controller.signal);
        if (!disposed && next.source_id === sourceId) {
          setRun(next);
          if (!terminalStatuses.has(next.status)) {
            timer = window.setTimeout(() => void poll(), pollIntervalMs);
          }
        }
      } catch (reason) {
        if (!disposed && !controller.signal.aborted && !isAbortError(reason)) {
          const apiError = asApiError(reason);
          if (apiError.code === "authentication_required") onAuthenticationRequired?.();
          else setError(apiError);
        }
      }
    };
    void poll();
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [onAuthenticationRequired, pollIntervalMs, run, sourceId]);

  const start = useCallback(async () => {
    if (sourceId === null || starting) return;
    startControllerRef.current?.abort();
    const controller = new AbortController();
    startControllerRef.current = controller;
    setStarting(true);
    setError(null);
    try {
      const created = await startResearch(sourceId, controller.signal);
      if (!controller.signal.aborted && created.source_id === sourceId) setRun(created);
    } catch (reason) {
      if (!controller.signal.aborted && !isAbortError(reason)) {
        const apiError = asApiError(reason);
        if (apiError.code === "authentication_required") onAuthenticationRequired?.();
        else setError(apiError);
      }
    } finally {
      if (startControllerRef.current === controller) startControllerRef.current = null;
      if (!controller.signal.aborted) setStarting(false);
    }
  }, [onAuthenticationRequired, sourceId, starting]);

  const adopt = useCallback((next: ResearchRun | null) => {
    if (next === null || next.source_id !== sourceId) return;
    setRun((current) => current?.id === next.id && current.status === next.status ? current : next);
  }, [sourceId]);

  return { adopt, error, run, start, starting };
}
