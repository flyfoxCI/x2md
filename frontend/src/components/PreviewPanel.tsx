import { useState } from "react";
import { createPortal } from "react-dom";

import { artifactDownloadUrl } from "../api";
import type { Artifact, PresentationSettings, Source } from "../types";
import { KnowledgeChat } from "./KnowledgeChat";
import { MarkdownPreview } from "./MarkdownPreview";

interface PreviewPanelProps {
  artifact: Artifact | null;
  isOverlayViewport: boolean;
  markdown: string;
  source: Source | null;
  presentation: PresentationSettings;
  onPresentationChange: (presentation: PresentationSettings) => void;
}

type MobileSurface = "editor" | "preview" | "chat";

export function PreviewPanel({
  artifact,
  isOverlayViewport,
  markdown,
  source,
  presentation,
  onPresentationChange,
}: PreviewPanelProps) {
  const [mobileSurface, setMobileSurface] = useState<MobileSurface>("editor");
  const isPreviewSurfaceVisible = !isOverlayViewport || mobileSurface === "preview";
  const isChatSurfaceVisible = !isOverlayViewport || mobileSurface === "chat";

  function selectMobileSurface(surface: Exclude<MobileSurface, "editor">) {
    setMobileSurface((current) => (current === surface ? "editor" : surface));
  }

  const panel = (
    <aside
      aria-label="Markdown 预览"
      className={`preview-panel${presentation.preview_device === "mobile" ? " is-mobile-device" : ""}`}
      data-mobile-surface={mobileSurface}
    >
      <div aria-label="移动工作区工具" className="mobile-workspace-tools" role="group">
        <button
          aria-controls="markdown-preview-surface"
          aria-expanded={mobileSurface === "preview"}
          className={mobileSurface === "preview" ? "is-active" : ""}
          onClick={() => selectMobileSurface("preview")}
          type="button"
        >
          预览
        </button>
        <button
          aria-controls="knowledge-chat-surface"
          aria-expanded={mobileSurface === "chat"}
          className={mobileSurface === "chat" ? "is-active" : ""}
          onClick={() => selectMobileSurface("chat")}
          type="button"
        >
          来源助手
        </button>
      </div>
      <div
        aria-hidden={!isPreviewSurfaceVisible || undefined}
        className="preview-heading"
        hidden={!isPreviewSurfaceVisible}
        inert={!isPreviewSurfaceVisible || undefined}
      >
        <h2>预览</h2>
        <div className="preview-actions">
          <label className="theme-select">
            <span>界面主题</span>
            <select
              aria-label="界面主题"
              onChange={(event) => onPresentationChange({
                ...presentation,
                theme: event.target.value as PresentationSettings["theme"],
              })}
              value={presentation.theme}
            >
              <option value="system">跟随系统</option>
              <option value="light">浅色</option>
              <option value="dark">深色</option>
            </select>
          </label>
          <div aria-label="预览设备" className="preview-device-toggle">
            <button
              aria-pressed={presentation.preview_device === "desktop"}
              onClick={() => onPresentationChange({ ...presentation, preview_device: "desktop" })}
              type="button"
            >
              桌面预览
            </button>
            <button
              aria-pressed={presentation.preview_device === "mobile"}
              onClick={() => onPresentationChange({ ...presentation, preview_device: "mobile" })}
              type="button"
            >
              手机预览
            </button>
          </div>
          {artifact ? <a className="download-link" href={artifactDownloadUrl(artifact.id)}>下载 Markdown</a> : null}
        </div>
      </div>
      <div
        aria-hidden={!isPreviewSurfaceVisible || undefined}
        className="preview-content"
        hidden={!isPreviewSurfaceVisible}
        id="markdown-preview-surface"
        inert={!isPreviewSurfaceVisible || undefined}
      >
        <article className="markdown-preview"><MarkdownPreview markdown={markdown} /></article>
      </div>
      <div
        aria-hidden={!isChatSurfaceVisible || undefined}
        hidden={!isChatSurfaceVisible}
        id="knowledge-chat-surface"
        inert={!isChatSurfaceVisible || undefined}
      >
        <KnowledgeChat key={source?.id ?? "no-source"} source={source} />
      </div>
    </aside>
  );

  return isOverlayViewport ? createPortal(panel, document.body) : panel;
}
