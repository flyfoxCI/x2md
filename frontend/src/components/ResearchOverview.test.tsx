import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResearchOverview } from "./ResearchOverview";

describe("ResearchOverview", () => {
  it("renders the executive conclusion, evidence metrics, and research judgment cards", () => {
    render(
      <ResearchOverview
        markdown={`## 研究摘要\n\n结论先行的项目判断。[E1]\n\n## 项目定位与问题\n\n解决复杂训练问题。[E1]\n\n## 核心能力与差异化\n\n模块化协议。[E2]\n\n## 局限、风险与未验证假设\n\n规模仍待验证。[E2]\n\n## 研究启发与关联方向\n\n可扩展到新环境。[E1]`}
        platform="github"
      />,
    );

    expect(screen.getByRole("heading", { name: "项目研究速览" })).toBeVisible();
    expect(screen.getByText(/结论先行的项目判断/)).toBeVisible();
    expect(screen.getByText("2 个证据引用")).toBeVisible();
    expect(screen.getByRole("heading", { name: "项目作用" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "局限边界" })).toBeVisible();
  });
});
