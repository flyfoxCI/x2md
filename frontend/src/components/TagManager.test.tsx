import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TagManager } from "./TagManager";

describe("TagManager", () => {
  it("separates suggestions from accepted labels and exposes explicit governance actions", () => {
    const onCreate = vi.fn();
    const onDecision = vi.fn();
    const onDelete = vi.fn();
    render(
      <TagManager
        assignments={[
          {
            id: 1,
            source_id: 1,
            research_run_id: 7,
            tag_id: 11,
            origin: "ai",
            status: "suggested",
            confidence: 0.8,
            created_at: "2026-08-23T00:00:00Z",
            updated_at: "2026-08-23T00:00:00Z",
          },
          {
            id: 2,
            source_id: 1,
            research_run_id: null,
            tag_id: 12,
            origin: "user",
            status: "accepted",
            confidence: null,
            created_at: "2026-08-23T00:00:00Z",
            updated_at: "2026-08-23T00:00:00Z",
          },
        ]}
        definitions={[
          { id: 11, slug: "rag", label: "检索增强生成", facet: "method", parent_id: null, is_system: true, description: null, created_at: "2026-08-23T00:00:00Z" },
          { id: 12, slug: "review", label: "内部评审", facet: null, parent_id: null, is_system: false, description: null, created_at: "2026-08-23T00:00:00Z" },
        ]}
        onCreate={onCreate}
        onDecision={onDecision}
        onDelete={onDelete}
        pending={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "接受 检索增强生成" }));
    fireEvent.click(screen.getByRole("button", { name: "移除 内部评审" }));
    fireEvent.change(screen.getByLabelText("新标签"), { target: { value: "复现" } });
    fireEvent.click(screen.getByRole("button", { name: "添加标签" }));

    expect(onDecision).toHaveBeenCalledWith(1, "accepted");
    expect(onDelete).toHaveBeenCalledWith(2);
    expect(onCreate).toHaveBeenCalledWith("复现");
  });
});
