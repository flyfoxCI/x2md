import { useEffect, useId, useState } from "react";

interface MermaidDiagramProps {
  chart: string;
}

const unsafeDirective = /%%\{|\bclick\b|javascript\s*:|<\/?[a-z][^>]*>/i;

function isSafeMermaidChart(chart: string): boolean {
  const normalized = chart.trim();
  const firstLine = normalized.split("\n", 1)[0]?.trim() ?? "";
  return normalized.length <= 3_000
    && /^(?:flowchart|graph)\s+(?:TB|TD|LR|RL)$/i.test(firstLine)
    && !unsafeDirective.test(normalized);
}

let runtimePromise: Promise<typeof import("mermaid").default> | null = null;

async function loadMermaid() {
  if (!runtimePromise) {
    runtimePromise = import("mermaid").then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "neutral",
        flowchart: { htmlLabels: false, useMaxWidth: true },
      });
      return mermaid;
    });
  }
  return runtimePromise;
}

export function MermaidDiagram({ chart }: MermaidDiagramProps) {
  const reactId = useId();
  const diagramId = `research-diagram-${reactId.replace(/[^a-zA-Z0-9-]/g, "")}`;
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const isSafe = isSafeMermaidChart(chart);

  useEffect(() => {
    if (!isSafe) return undefined;
    let active = true;
    setSvg("");
    setFailed(false);
    void loadMermaid()
      .then((mermaid) => mermaid.render(diagramId, chart.trim()))
      .then((result) => {
        if (active) setSvg(result.svg);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [chart, diagramId, isSafe]);

  if (!isSafe) {
    return (
      <div className="mermaid-fallback" role="note">
        <strong>图示不符合安全规则，已保留原始结构</strong>
        <pre><code>{chart}</code></pre>
      </div>
    );
  }

  if (failed) {
    return (
      <div className="mermaid-fallback" role="note">
        <strong>图示暂时无法渲染，已保留原始结构</strong>
        <pre><code>{chart}</code></pre>
      </div>
    );
  }
  if (!svg) return <div className="mermaid-loading" role="status">正在绘制研究综述…</div>;

  return (
    <figure aria-label="研究一图综述" className="mermaid-diagram">
      {/* Mermaid strict mode sanitizes this generated SVG; imported raw HTML remains disabled. */}
      <div dangerouslySetInnerHTML={{ __html: svg }} />
      <figcaption>基于报告证据生成的结构综述</figcaption>
    </figure>
  );
}
