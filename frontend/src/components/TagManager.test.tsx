import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TagManager } from "./TagManager";

describe("TagManager", () => {
  it("renders automatic tags as read-only chips without governance controls", () => {
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
      />,
    );

    expect(screen.getByText("检索增强生成")).toBeVisible();
    expect(screen.getByText("内部评审")).toBeVisible();
    expect(screen.queryByRole("button", { name: "添加标签" })).toBeNull();
    expect(screen.queryByLabelText("新标签")).toBeNull();
    expect(screen.queryByRole("button", { name: "接受 检索增强生成" })).toBeNull();
  });

  it("renders nothing when a source has no tags", () => {
    const { container } = render(<TagManager assignments={[]} definitions={[]} />);
    expect(container.querySelector(".tag-manager")).toBeNull();
  });
});
