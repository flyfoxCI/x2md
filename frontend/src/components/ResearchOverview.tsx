import { SafeMarkdown } from "./SafeMarkdown";
import { parseResearchOverview } from "./researchMarkdown";

interface ResearchOverviewProps {
  markdown: string;
  platform: string;
}
export function ResearchOverview({ markdown, platform }: ResearchOverviewProps) {
  const overview = parseResearchOverview(markdown, platform);

  return (
    <article className="research-overview">
      <header className="research-overview-hero">
        <span className="research-overview-eyebrow">{overview.typeLabel}</span>
        <h2>{overview.title}</h2>
        <div className="research-overview-summary"><SafeMarkdown>{overview.summary}</SafeMarkdown></div>
        <div aria-label="研究报告指标" className="research-overview-metrics">
          <span>{overview.citationCount} 个证据引用</span>
          <span>{overview.sectionCount} 个研究章节</span>
          <span className={overview.hasDiagram ? "is-ready" : "is-legacy"}>
            {overview.hasDiagram ? "含一图综述" : "旧版报告 · 重新研究可生成图示"}
          </span>
        </div>
      </header>
      <div className="research-insight-grid">
        {overview.cards.map((card, index) => (
          <section className="research-insight-card" key={`${card.label}-${card.heading}`}>
            <div className="research-insight-heading">
              <span aria-hidden="true">0{index + 1}</span>
              <div>
                <h3>{card.label}</h3>
                <p>{card.heading}</p>
              </div>
            </div>
            <div className="research-insight-copy"><SafeMarkdown>{card.markdown}</SafeMarkdown></div>
          </section>
        ))}
      </div>
    </article>
  );
}
