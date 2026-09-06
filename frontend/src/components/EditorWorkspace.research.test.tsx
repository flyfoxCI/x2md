import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SourceDetail } from "../types";
import { EditorWorkspace } from "./EditorWorkspace";

const report = `## 研究摘要

这是一个值得验证的训练项目。[E1]

## 项目定位与问题

解决环境标准化问题。[E1]

## 核心能力与差异化

采用模块化协议。[E1]

## 局限、风险与未验证假设

规模仍待验证。[E1]

## 研究启发与关联方向

可研究跨环境迁移。[E1]`;

const detail: SourceDetail = {
  source: {
    id: 1,
    canonical_url: "https://github.com/example/project",
    platform: "github",
    title: "Example Project",
    author: null,
    published_at: null,
    raw_text: "source",
    source_markdown: "# Source",
    metadata_json: {},
    import_status: "ready",
    failure_reason: null,
    created_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z",
  },
  artifacts: [{
    id: 9,
    source_id: 1,
    kind: "research",
    title: "Research",
    markdown: report,
    language: "zh",
    parent_artifact_id: null,
    research_run_id: 2,
    model_metadata_json: {},
    created_at: "2026-08-30T00:00:00Z",
    updated_at: "2026-08-30T00:00:00Z",
  }],
};

describe("EditorWorkspace research reading mode", () => {
  it("shows a research overview by default and keeps full Markdown editable on demand", () => {
    const onSave = vi.fn();
    render(
      <EditorWorkspace
        currentMarkdown={report}
        deriving={null}
        detail={detail}
        loading={false}
        onContentChange={vi.fn()}
        onDerive={vi.fn()}
        onSave={onSave}
        saving={false}
        selectedArtifact={detail.artifacts[0]}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "深度研究" }));

    expect(screen.getByRole("heading", { name: "项目研究速览" })).toBeVisible();
    expect(screen.queryByLabelText("Markdown 内容")).not.toBeInTheDocument();
    expect(screen.getByText("右侧展示完整研究报告")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "编辑完整报告" }));
    expect(screen.getByLabelText("Markdown 内容")).toHaveValue(report);
    fireEvent.click(screen.getByRole("button", { name: "保存版本" }));
    expect(onSave).toHaveBeenCalledWith(detail.artifacts[0], report);

    fireEvent.click(screen.getByRole("button", { name: "返回研究速览" }));
    expect(screen.queryByLabelText("Markdown 内容")).not.toBeInTheDocument();
  });
});
