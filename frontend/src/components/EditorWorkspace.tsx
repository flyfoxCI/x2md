import { useEffect, useMemo, useState, type KeyboardEvent } from "react";

import type { Artifact, ArtifactKind, DerivationKind, SourceDetail } from "../types";
import { rootArtifactKind } from "./artifactLineage";
import { ResearchOverview } from "./ResearchOverview";

export type WorkspaceTab = "original" | "translation" | "summary" | "skill" | "research";

interface EditorWorkspaceProps {
  detail: SourceDetail | null;
  loading: boolean;
  deriving: WorkspaceTab | null;
  saving: boolean;
  onDerive: (kind: DerivationKind) => void;
  onSave: (artifact: Artifact, markdown: string) => void;
  onContentChange: (markdown: string, artifact: Artifact | null) => void;
  currentMarkdown: string;
  selectedArtifact: Artifact | null;
}

interface TabDefinition {
  id: WorkspaceTab;
  label: string;
  artifactKind?: ArtifactKind;
}

const tabs: readonly TabDefinition[] = [
  { id: "original", label: "原文" },
  { id: "translation", label: "中文翻译", artifactKind: "translation" },
  { id: "summary", label: "知识摘要", artifactKind: "summary" },
  { id: "skill", label: "Distilled Skill", artifactKind: "skill" },
  { id: "research", label: "深度研究", artifactKind: "research" },
];

export function EditorWorkspace({
  detail,
  loading,
  deriving,
  saving,
  onDerive,
  onSave,
  onContentChange,
  currentMarkdown,
  selectedArtifact,
}: EditorWorkspaceProps) {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("original");
  const [researchEditing, setResearchEditing] = useState(false);

  useEffect(() => {
    setActiveTab("original");
    setResearchEditing(false);
  }, [detail?.source.id]);

  const activeDefinition = useMemo(
    () => tabs.find((tab) => tab.id === activeTab) ?? tabs[0],
    [activeTab],
  );
  const activeArtifact = findArtifact(detail, activeDefinition);
  const canEdit = activeArtifact !== null;
  const isResearchOverview = activeDefinition.id === "research" && canEdit && !researchEditing;

  function selectTab(tab: WorkspaceTab) {
    setActiveTab(tab);
    setResearchEditing(false);
  }

  function moveTab(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") {
      return;
    }
    event.preventDefault();
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex];
    selectTab(nextTab.id);
    document.getElementById(`tab-${nextTab.id}`)?.focus();
  }

  useEffect(() => {
    if (!detail) {
      onContentChange("", null);
      return;
    }
    if (activeDefinition.id === "original") {
      onContentChange(detail.source.source_markdown || detail.source.raw_text, null);
      return;
    }
    onContentChange(activeArtifact?.markdown ?? "", activeArtifact ?? null);
  }, [activeArtifact, activeDefinition.id, detail, onContentChange]);

  if (loading) {
    return <section className="editor-workspace is-loading" aria-label="内容工作区"><p role="status">正在打开来源…</p></section>;
  }
  if (!detail) {
    return (
      <section className="editor-workspace empty-workspace" aria-label="内容工作区">
        <div>
          <span aria-hidden="true">↙</span>
          <h2>从一个专家链接开始</h2>
          <p>导入公开来源后，原文、中文翻译、知识摘要、Skill 和深度研究都会在这里沉淀为可编辑 Markdown。</p>
        </div>
      </section>
    );
  }

  return (
    <section className="editor-workspace" aria-label="内容工作区">
      <div className="source-provenance">
        <span aria-hidden="true" className="provenance-mark">{platformSymbol(detail.source.platform)}</span>
        <div>
          <h2>{detail.source.title}</h2>
          <p>{detail.source.platform} · <a href={detail.source.canonical_url} rel="noreferrer" target="_blank">查看原始来源</a></p>
        </div>
      </div>
      <div className="workspace-header">
        <div aria-label="内容视图" className="artifact-tabs" role="tablist">
          {tabs.map((tab, index) => (
            <button
              aria-controls="markdown-editor"
              aria-selected={activeTab === tab.id}
              className={activeTab === tab.id ? "is-active" : ""}
              id={`tab-${tab.id}`}
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(event) => moveTab(event, index)}
              role="tab"
              tabIndex={activeTab === tab.id ? 0 : -1}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
        {canEdit ? (
          <div className="workspace-actions">
            {activeDefinition.id === "research" ? (
              <button
                className="secondary-button"
                onClick={() => setResearchEditing((editing) => !editing)}
                type="button"
              >
                {researchEditing ? "返回研究速览" : "编辑完整报告"}
              </button>
            ) : null}
            {!isResearchOverview ? (
              <button
                className="primary-button save-button"
                disabled={saving}
                onClick={() => onSave(activeArtifact, currentMarkdown)}
                type="button"
              >
                {saving ? "保存中…" : "保存版本"}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      <div
        aria-labelledby={`tab-${activeDefinition.id}`}
        className="markdown-editor-wrap"
        id="markdown-editor"
        role="tabpanel"
      >
        {activeDefinition.artifactKind && !activeArtifact ? (
          <div className="derive-empty">
            <p>{activeDefinition.label}{activeDefinition.id === "research" ? "报告尚未生成，请先在上方启动研究。" : "尚未生成。"}</p>
            {activeDefinition.id !== "research" ? <button
              className="primary-button"
              disabled={deriving !== null}
              onClick={() => onDerive(activeDefinition.artifactKind as DerivationKind)}
              type="button"
            >
              {deriving === activeTab ? "正在生成…" : `生成${activeDefinition.label}`}
            </button> : null}
          </div>
        ) : isResearchOverview ? (
          <ResearchOverview
            markdown={currentMarkdown || activeArtifact.markdown}
            platform={detail.source.platform}
          />
        ) : (
          <textarea
            aria-label="Markdown 内容"
            onChange={(event) => onContentChange(event.target.value, selectedArtifact)}
            readOnly={!canEdit}
            spellCheck={false}
            value={currentMarkdown}
          />
        )}
      </div>
      <footer className="editor-footer">
        <span>{currentMarkdown.length.toLocaleString()} 字符</span>
        <span>{isResearchOverview ? "右侧展示完整研究报告" : canEdit ? activeDefinition.id === "research" ? "编辑后的研究报告不再自动验证引用" : "编辑会保存为新版本" : "原始来源保持不变"}</span>
      </footer>
    </section>
  );
}

function findArtifact(detail: SourceDetail | null, tab: TabDefinition): Artifact | null {
  if (!detail || !tab.artifactKind) {
    return null;
  }
  const byId = new Map(detail.artifacts.map((artifact) => [artifact.id, artifact]));
  const candidates = detail.artifacts.filter(
    (artifact) => rootArtifactKind(artifact, byId) === tab.artifactKind,
  );
  return candidates.at(-1) ?? null;
}

function platformSymbol(platform: string): string {
  if (platform === "github") return "◉";
  if (platform === "youtube") return "▶";
  if (platform === "arxiv") return "a";
  if (platform === "x") return "𝕏";
  return "◌";
}
