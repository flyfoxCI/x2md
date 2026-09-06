export interface ResearchOverviewCard {
  label: string;
  heading: string;
  markdown: string;
}
export interface ResearchOverviewData {
  title: string;
  typeLabel: string;
  summary: string;
  cards: ResearchOverviewCard[];
  citationCount: number;
  sectionCount: number;
  hasDiagram: boolean;
}

interface OverviewContract {
  title: string;
  typeLabel: string;
  summaryHeadings: readonly string[];
  cards: readonly { label: string; headings: readonly string[] }[];
}

const contracts: Record<string, OverviewContract> = {
  github: {
    title: "项目研究速览",
    typeLabel: "GitHub · 工程研究",
    summaryHeadings: ["研究摘要", "核心贡献", "项目定位与问题", "背景与目标", "研究范围与覆盖率"],
    cards: [
      { label: "项目作用", headings: ["项目定位与问题", "背景与目标"] },
      { label: "核心价值", headings: ["核心能力与差异化", "核心贡献", "关键结果"] },
      { label: "局限边界", headings: ["局限、风险与未验证假设", "局限与风险"] },
      { label: "研发启发", headings: ["研究启发与关联方向", "复现与应用建议"] },
    ],
  },
  arxiv: {
    title: "论文研究速览",
    typeLabel: "arXiv · 论文研究",
    summaryHeadings: ["研究摘要", "研究问题与论文主张", "核心贡献", "背景与目标"],
    cards: [
      { label: "研究问题", headings: ["研究问题与论文主张", "背景与目标"] },
      { label: "方法贡献", headings: ["方法原理与关键创新", "核心贡献", "方法或架构"] },
      { label: "证据结论", headings: ["结果、对比与消融", "关键结果", "结论有效范围"] },
      { label: "开放问题", headings: ["局限、风险与开放问题", "局限与风险", "研究启发与相关工作脉络"] },
    ],
  },
  huggingface: {
    title: "技术内容速览",
    typeLabel: "Hugging Face · 技术研究",
    summaryHeadings: ["研究摘要", "核心观点与价值主张", "核心贡献", "背景与目标"],
    cards: [
      { label: "内容价值", headings: ["内容定位与目标读者", "背景与目标"] },
      { label: "技术要点", headings: ["核心观点与价值主张", "技术路线或产品机制", "核心贡献"] },
      { label: "适用边界", headings: ["局限、风险与信息缺口", "局限与风险"] },
      { label: "延伸方向", headings: ["研究启发与延伸阅读方向", "复现与应用建议"] },
    ],
  },
};

const headingPattern = /^## (.+?)\s*$/gm;

export function parseResearchOverview(markdown: string, platform: string): ResearchOverviewData {
  const contract = contracts[platform] ?? contracts.github;
  const sections = parseSections(markdown);
  const summary = firstAvailable(sections, contract.summaryHeadings) || firstSubstantiveSection(sections);
  const cards = contract.cards.flatMap((card) => {
    const found = firstAvailableEntry(sections, card.headings);
    return found ? [{ label: card.label, heading: found[0], markdown: excerpt(found[1]) }] : [];
  });
  const citations = new Set(Array.from(markdown.matchAll(/\[E([1-9][0-9]*)\]/g), (match) => match[1]));

  return {
    title: contract.title,
    typeLabel: contract.typeLabel,
    summary: excerpt(summary) || "报告已生成，但暂未识别到可提取的摘要段落。请在右侧阅读完整报告。",
    cards,
    citationCount: citations.size,
    sectionCount: sections.size,
    hasDiagram: /```mermaid\s*\n/i.test(markdown),
  };
}

function parseSections(markdown: string): Map<string, string> {
  const matches = Array.from(markdown.matchAll(headingPattern));
  return new Map(matches.map((match, index) => {
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? markdown.length;
    return [match[1].trim(), markdown.slice(start, end).trim()];
  }));
}

function firstAvailable(sections: Map<string, string>, headings: readonly string[]): string {
  return firstAvailableEntry(sections, headings)?.[1] ?? "";
}

function firstAvailableEntry(
  sections: Map<string, string>, headings: readonly string[],
): [string, string] | undefined {
  for (const heading of headings) {
    const body = sections.get(heading);
    if (body?.trim()) return [heading, body];
  }
  return undefined;
}

function firstSubstantiveSection(sections: Map<string, string>): string {
  for (const [heading, body] of sections) {
    if (!["一图综述", "标签", "证据索引"].includes(heading) && body.trim()) return body;
  }
  return "";
}

function excerpt(markdown: string): string {
  const withoutDiagram = markdown.replace(/```mermaid[\s\S]*?```/gi, "").trim();
  if (withoutDiagram.length <= 900) return withoutDiagram;
  return `${withoutDiagram.slice(0, 897).trimEnd()}…`;
}
