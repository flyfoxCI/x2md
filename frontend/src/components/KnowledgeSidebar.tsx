import { useEffect, useLayoutEffect, useRef, type ChangeEvent } from "react";

import type { Source } from "../types";

interface KnowledgeSidebarProps {
  sources: Source[];
  total: number;
  loading: boolean;
  query: string;
  selectedSourceId: number | null;
  isCompactViewport: boolean;
  mobileOpen: boolean;
  onQueryChange: (query: string) => void;
  onSelect: (source: Source) => void;
  onOpenImport: (trigger: HTMLButtonElement) => void;
  onCloseMobile: () => void;
  onReturnFocus: () => void;
}

const platformLabels: Record<string, string> = {
  arxiv: "arXiv",
  github: "GitHub",
  huggingface: "Hugging Face",
  web: "网页",
  x: "X",
  youtube: "YouTube",
};

export function KnowledgeSidebar({
  sources,
  total,
  loading,
  query,
  selectedSourceId,
  isCompactViewport,
  mobileOpen,
  onQueryChange,
  onSelect,
  onOpenImport,
  onCloseMobile,
  onReturnFocus,
}: KnowledgeSidebarProps) {
  const sidebarRef = useRef<HTMLElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const isMobileHidden = isCompactViewport && !mobileOpen;

  useLayoutEffect(() => {
    if (isMobileHidden && sidebarRef.current?.contains(document.activeElement)) {
      onReturnFocus();
    }
  }, [isMobileHidden, onReturnFocus]);

  useEffect(() => {
    if (isCompactViewport && mobileOpen) {
      searchInputRef.current?.focus();
    }
  }, [isCompactViewport, mobileOpen]);

  function updateQuery(event: ChangeEvent<HTMLInputElement>) {
    onQueryChange(event.target.value);
  }

  function selectSource(source: Source) {
    if (isCompactViewport) {
      onCloseMobile();
    }
    onSelect(source);
  }

  return (
    <aside
      aria-hidden={isMobileHidden || undefined}
      className={`knowledge-sidebar${mobileOpen ? " is-mobile-open" : ""}`}
      inert={isMobileHidden || undefined}
      ref={sidebarRef}
    >
      <div className="sidebar-heading">
        <div>
          <span aria-hidden="true" className="sidebar-symbol">▣</span>
          <h2>知识库</h2>
        </div>
        <div className="sidebar-heading-actions">
          <button
            aria-label="导入新来源"
            className="icon-button"
            onClick={(event) => onOpenImport(event.currentTarget)}
            type="button"
          >
            ＋
          </button>
          <button aria-label="关闭知识库" className="close-library-button icon-button" onClick={onCloseMobile} type="button">×</button>
        </div>
      </div>
      <label className="search-field" htmlFor="library-search">
        <span aria-hidden="true">⌕</span>
        <input
          id="library-search"
          onChange={updateQuery}
          placeholder="搜索知识库…"
          ref={searchInputRef}
          type="search"
          value={query}
        />
      </label>
      <nav aria-label="知识库筛选" className="sidebar-nav">
        <span>全部来源 <strong>{total}</strong></span>
        <span>最近导入</span>
        <span>我的 Skill</span>
      </nav>
      <div className="sidebar-list-heading">来源列表</div>
      <div aria-busy={loading} className="source-list">
        {loading ? <p className="sidebar-muted" role="status">正在加载来源…</p> : null}
        {!loading && sources.length === 0 ? <p className="sidebar-muted">还没有已导入的来源。</p> : null}
        {sources.map((source) => (
          <button
            aria-current={selectedSourceId === source.id ? "page" : undefined}
            className={`source-row${selectedSourceId === source.id ? " is-selected" : ""}`}
            key={source.id}
            onClick={() => selectSource(source)}
            type="button"
          >
            <span aria-hidden="true" className={`platform-mark platform-${source.platform}`}>{platformMark(source.platform)}</span>
            <span className="source-row-copy">
              <strong>{source.title}</strong>
              <span>{platformLabels[source.platform] ?? source.platform}{source.author ? ` · ${source.author}` : ""}</span>
              {source.import_status !== "ready" ? <em>{source.import_status === "partial" ? "部分导入" : "已受限"}</em> : null}
            </span>
            <span aria-hidden="true" className="row-more">⋮</span>
          </button>
        ))}
      </div>
    </aside>
  );
}

function platformMark(platform: string): string {
  if (platform === "github") return "◉";
  if (platform === "youtube") return "▶";
  if (platform === "arxiv") return "a";
  if (platform === "huggingface") return "⌁";
  if (platform === "x") return "𝕏";
  return "◌";
}
