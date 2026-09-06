import { describe, expect, it } from "vitest";

import { parseResearchOverview } from "./researchMarkdown";

const githubReport = `## 研究摘要

这是一个面向智能体训练的工程系统，核心判断有证据支持。[E1]

## 一图综述

\`\`\`mermaid
flowchart LR
A["环境"] --> B["训练"]
\`\`\`

## 研究范围与证据质量

覆盖 8 份材料。

## 项目定位与问题

项目解决训练环境标准化问题。[E1]

## 核心能力与差异化

协议与运行时解耦。[E2]

## 系统架构与模块边界

分为环境、编排和训练模块。[E2]

## 关键流程与实现机制

流程可追溯。[E3]

## 工程质量与可复现性

提供测试与容器配置。[E3]

## 应用场景与采用建议

适合研究团队。[E1]

## 局限、风险与未验证假设

大规模稳定性尚未验证。[E3]

## 研究启发与关联方向

可研究跨环境迁移。[E2]

## 结论

值得小规模验证。[E1]

## 标签

- Agentic RL

## 证据索引

- [E1] README
- [E2] runtime.py
- [E3] tests
`;

describe("parseResearchOverview", () => {
  it("extracts a conclusion-first GitHub overview and unique evidence metrics", () => {
    const overview = parseResearchOverview(githubReport, "github");

    expect(overview.title).toBe("项目研究速览");
    expect(overview.summary).toContain("工程系统");
    expect(overview.cards.map((card) => card.label)).toEqual([
      "项目作用",
      "核心价值",
      "局限边界",
      "研发启发",
    ]);
    expect(overview.cards[0].markdown).toContain("训练环境标准化");
    expect(overview.citationCount).toBe(3);
    expect(overview.sectionCount).toBe(14);
    expect(overview.hasDiagram).toBe(true);
  });

  it("keeps legacy reports useful through heading fallbacks", () => {
    const overview = parseResearchOverview(
      `## 研究范围与覆盖率\n\n覆盖有限。\n\n## 背景与目标\n\n旧版项目目标。[E1]\n\n## 核心贡献\n\n旧版贡献。[E1]\n\n## 局限与风险\n\n旧版局限。[E1]`,
      "github",
    );

    expect(overview.summary).toContain("旧版贡献");
    expect(overview.cards.some((card) => card.markdown.includes("旧版局限"))).toBe(true);
    expect(overview.hasDiagram).toBe(false);
  });

  it("uses research vocabulary appropriate to papers and technical content", () => {
    expect(parseResearchOverview("## 研究摘要\n\n论文摘要。[E1]", "arxiv").title).toBe("论文研究速览");
    expect(parseResearchOverview("## 研究摘要\n\n博客摘要。[E1]", "huggingface").title).toBe("技术内容速览");
  });
});
