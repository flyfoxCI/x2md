import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResearchPanel } from "./ResearchPanel";

const run = {
  id: 7,
  source_id: 1,
  trigger: "manual",
  status: "partial" as const,
  phase: null,
  budget_json: {},
  coverage_json: { complete: false, reason: "tree_truncated" },
  attempt_count: 1,
  max_attempts: 2,
  next_attempt_at: null,
  failure_code: null,
  provider_metadata_json: {},
  started_at: null,
  finished_at: null,
  created_at: "2026-08-23T00:00:00Z",
  updated_at: "2026-08-23T00:00:00Z",
};

describe("ResearchPanel", () => {
  it("starts a study and presents partial coverage with evidence controls", () => {
    const onStart = vi.fn();
    const onAutoStartChange = vi.fn();
    const onSelectEvidence = vi.fn();
    render(
      <ResearchPanel
        evidence={[
          {
            id: 1,
            research_run_id: 7,
            source_id: 1,
            locator: "github://owner/repo@sha/README.md",
            kind: "repository_file",
            title: "README.md",
            ordinal: 0,
            source_revision: "sha",
            content: "evidence",
            digest_markdown: "note",
            status: "included",
            exclusion_reason: null,
            created_at: "2026-08-23T00:00:00Z",
          },
          {
            id: 2,
            research_run_id: 7,
            source_id: 1,
            locator: "github://owner/repo@sha/model.bin",
            kind: "repository_file",
            title: "model.bin",
            ordinal: 1,
            source_revision: "sha",
            content: null,
            digest_markdown: null,
            status: "excluded",
            exclusion_reason: "binary_or_unsupported",
            created_at: "2026-08-23T00:00:00Z",
          },
        ]}
        onSelectEvidence={onSelectEvidence}
        onStart={onStart}
        onAutoStartChange={onAutoStartChange}
        autoStart={false}
        autoStartPending={false}
        reportMarkdown="结论可追溯。[E1] 无效 [E99]"
        run={run}
        sourceSupported
        starting={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "开始深度研究" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "自动研究新导入" }));
    fireEvent.click(screen.getByRole("button", { name: "查看证据 E1" }));
    fireEvent.click(screen.getByText("证据清单（2）"));

    expect(onStart).toHaveBeenCalledOnce();
    expect(onAutoStartChange).toHaveBeenCalledWith(true);
    expect(screen.getByText("部分覆盖")).toBeVisible();
    expect(screen.getByText("tree_truncated")).toBeVisible();
    expect(screen.getByText("binary_or_unsupported")).toBeVisible();
    expect(onSelectEvidence).toHaveBeenCalledWith(1);
    expect(screen.queryByRole("button", { name: "查看证据 E99" })).not.toBeInTheDocument();
  });
});
