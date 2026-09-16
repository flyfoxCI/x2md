import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ChangeEvent } from "react";

import type { Source, TagDefinition } from "../types";

interface KnowledgeSidebarProps {
  sources: Source[];
  total: number;
  loading: boolean;
  query: string;
  tagDefinitions: TagDefinition[];
  tagFilter: string;
  selectedSourceId: number | null;
  isCompactViewport: boolean;
  mobileOpen: boolean;
  onQueryChange: (query: string) => void;
  onTagFilterChange: (tag: string) => void;
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
  tagDefinitions,
  tagFilter,
  selectedSourceId,
  isCompactViewport,
  mobileOpen,
  onQueryChange,
  onTagFilterChange,
  onSelect,
  onOpenImport,
  onCloseMobile,
  onReturnFocus,
}: KnowledgeSidebarProps) {
  const sidebarRef = useRef<HTMLElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<ReadonlySet<string>>(new Set());
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

  const sourceGroups = useMemo(() => {
    const labelOf = new Map(tagDefinitions.map((tag) => [tag.id, tag.label]));
    const groups = new Map<string, Source[]>();
    for (const source of sources) {
      const key = source.tag_labels?.[0] ?? "未分类";
      const bucket = groups.get(key);
      if (bucket) {
        bucket.push(source);
      } else {
        groups.set(key, [source]);
      }
    }
    return [...groups.entries()];
  }, [sources, tagDefinitions]);

  function toggleGroup(label: string) {
    setCollapsedGroups((current) => {
      const next = new Set(current);
      if (current.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
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
      <nav aria-label="分类目录" className="category-directory">
        <div className="directory-heading">分类目录</div>
        <div className="directory-chips">
          <button
            aria-pressed={tagFilter === ""}
            className={`directory-chip${tagFilter === "" ? " is-active" : ""}`}
            onClick={() => onTagFilterChange("")}
            type="button"
          >
            全部 <strong>{total}</strong>
          </button>
          {tagDefinitions.filter((tag) => (tag.source_count ?? 0) > 0).map((tag) => (
            <button
              aria-pressed={tagFilter === tag.slug}
              className={`directory-chip${tagFilter === tag.slug ? " is-active" : ""}`}
              key={tag.id}
              onClick={() => onTagFilterChange(tagFilter === tag.slug ? "" : tag.slug)}
              type="button"
            >
              {tag.label} <strong>{tag.source_count}</strong>
            </button>
          ))}
        </div>
      </nav>
      <div className="sidebar-list-heading">来源列表</div>
      <div aria-busy={loading} className="source-list">
        {loading ? <p className="sidebar-muted" role="status">正在加载来源…</p> : null}
        {!loading && sources.length === 0 ? <p className="sidebar-muted">还没有已导入的来源。</p> : null}
        {sourceGroups.map(([label, groupSources]) => (
          <section className="source-group" key={label}>
            <button
              aria-expanded={!collapsedGroups.has(label)}
              className="source-group-heading"
              onClick={() => toggleGroup(label)}
              type="button"
            >
              <span>{label}</span>
              <strong>{label === "未分类" ? groupSources.length : (tagDefinitions.find((tag) => tag.label === label)?.source_count ?? groupSources.length)}</strong>
              <span aria-hidden="true" className="group-caret">{collapsedGroups.has(label) ? "▸" : "▾"}</span>
            </button>
            {!collapsedGroups.has(label) ? groupSources.map((source) => (
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
            )) : null}
          </section>
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