import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Artifact } from "../types";
import { PreviewPanel } from "./PreviewPanel";

const artifact: Artifact = {
  id: 1,
  source_id: 1,
  kind: "research",
  title: "Research",
  markdown: "## 研究摘要\n\n结论。[E1]",
  language: "zh",
  parent_artifact_id: null,
  research_run_id: 1,
  model_metadata_json: {},
  created_at: "2026-08-30T00:00:00Z",
  updated_at: "2026-08-30T00:00:00Z",
};

describe("PreviewPanel", () => {
  it("names the right-hand surface as the full report for research artifacts", () => {
    render(
      <PreviewPanel
        artifact={artifact}
        isOverlayViewport={false}
        markdown={artifact.markdown}
        onPresentationChange={vi.fn()}
        presentation={{ theme: "system", preview_device: "desktop" }}
        source={null}
      />,
    );

    expect(screen.getByRole("heading", { name: "完整研究报告" })).toBeVisible();
  });
});
