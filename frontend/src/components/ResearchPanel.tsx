import type { ResearchEvidence, ResearchRun } from "../types";

interface ResearchPanelProps {
  sourceSupported: boolean;
  run: ResearchRun | null;
  evidence: ResearchEvidence[];
  reportMarkdown: string | null;
  starting: boolean;
  autoStart: boolean;
  autoStartPending: boolean;
  onStart: () => void;
  onAutoStartChange: (autoStart: boolean) => void;
  onSelectEvidence: (evidenceId: number) => void;
}

const statusCopy: Record<ResearchRun["status"], string> = {
  queued: "已排队",
  running: "研究中",
  completed: "已完成",
  partial: "部分覆盖",
  blocked: "已阻止",
  failed: "失败",
};

export function ResearchPanel({
  sourceSupported,
  run,
  evidence,
  reportMarkdown,
  starting,
  autoStart,
  autoStartPending,
  onStart,
  onAutoStartChange,
  onSelectEvidence,
}: ResearchPanelProps) {
  const evidenceIds = new Set(evidence.map((item) => item.id));
  const citations = [...new Set(
    [...(reportMarkdown ?? "").matchAll(/\[E([1-9]\d*)\]/g)].map((match) => Number(match[1])),
  )].filter((id) => evidenceIds.has(id));
  const coverageReason = typeof run?.coverage_json.reason === "string"
    ? run.coverage_json.reason
    : null;

  if (!sourceSupported) return null;
  return (
    <section aria-label="深度研究" className="research-panel">
      <div className="research-heading">
        <div>
          <span>深度研究</span>
          <p>证据优先 · 可追溯 · 有界采集</p>
        </div>
        <button className="secondary-button" disabled={starting || run?.status === "running" || run?.status === "queued"} onClick={onStart} type="button">
          {starting ? "正在入队…" : run?.status === "running" || run?.status === "queued" ? "研究进行中" : "开始深度研究"}
        </button>
      </div>
      <label className="research-auto-start">
        <input
          aria-label="自动研究新导入"
          checked={autoStart}
          disabled={autoStartPending}
          onChange={(event) => onAutoStartChange(event.target.checked)}
          type="checkbox"
        />
        <span>新导入后自动研究</span>
        <small>启用后请重启服务以启动后台工作器</small>
      </label>
      {run ? (
        <div className="research-summary">
          <strong className={`research-status is-${run.status}`}>{statusCopy[run.status]}</strong>
          <span>{run.phase ?? (coverageReason ? "覆盖范围已记录" : "等待证据")}</span>
          {coverageReason ? <code>{coverageReason}</code> : null}
          {run.failure_code ? <span className="research-failure">{run.failure_code}</span> : null}
        </div>
      ) : <p className="research-empty">尚未建立研究运行。系统会保留采集范围和无法覆盖的材料。</p>}
      {citations.length ? (
        <div className="research-citations" aria-label="报告引用">
          {citations.map((id) => <button key={id} onClick={() => onSelectEvidence(id)} type="button">查看证据 E{id}</button>)}
        </div>
      ) : null}
      {evidence.length ? (
        <details className="research-evidence">
          <summary>证据清单（{evidence.length}）</summary>
          <ul>
            {evidence.map((item) => (
              <li key={item.id}>
                <button onClick={() => onSelectEvidence(item.id)} type="button">E{item.id}</button>
                <span>{item.title ?? item.locator}</span>
                <em className={`evidence-${item.status}`}>{item.status === "included" ? "已采集" : item.exclusion_reason ?? "已排除"}</em>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
