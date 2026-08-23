import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getResearchRun, startResearch } from "../api";
import type { ResearchRun } from "../types";
import { useResearchRun } from "./useResearchRun";

vi.mock("../api", () => ({
  getResearchRun: vi.fn(),
  startResearch: vi.fn(),
}));

const mockedGetResearchRun = vi.mocked(getResearchRun);
const mockedStartResearch = vi.mocked(startResearch);

function run(status: ResearchRun["status"], sourceId = 1): ResearchRun {
  return {
    id: 7,
    source_id: sourceId,
    trigger: "manual",
    status,
    phase: status === "running" ? "collecting" : null,
    budget_json: {},
    coverage_json: {},
    attempt_count: 0,
    max_attempts: 2,
    next_attempt_at: null,
    failure_code: null,
    provider_metadata_json: {},
    started_at: null,
    finished_at: null,
    created_at: "2026-08-23T00:00:00Z",
    updated_at: "2026-08-23T00:00:00Z",
  };
}

describe("useResearchRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedStartResearch.mockResolvedValue(run("queued"));
    mockedGetResearchRun.mockResolvedValue(run("completed"));
  });

  it("starts a run and stops polling after a terminal state", async () => {
    const { result } = renderHook(() => useResearchRun(1, { pollIntervalMs: 1 }));

    await act(async () => {
      await result.current.start();
    });

    await waitFor(() => expect(result.current.run?.status).toBe("completed"));
    expect(mockedStartResearch).toHaveBeenCalledWith(1, expect.any(AbortSignal));
    expect(mockedGetResearchRun).toHaveBeenCalledTimes(1);
  });

  it("aborts polling when the selected source changes or the hook unmounts", async () => {
    let pollingSignal: AbortSignal | undefined;
    mockedGetResearchRun.mockImplementation(async (_runId, signal) => {
      pollingSignal = signal;
      return new Promise(() => undefined);
    });
    const { result, rerender, unmount } = renderHook(
      ({ sourceId }) => useResearchRun(sourceId, { pollIntervalMs: 1 }),
      { initialProps: { sourceId: 1 } },
    );

    await act(async () => {
      await result.current.start();
    });
    await waitFor(() => expect(pollingSignal).toBeDefined());
    rerender({ sourceId: 2 });
    await waitFor(() => expect(pollingSignal?.aborted).toBe(true));
    unmount();
  });
});
