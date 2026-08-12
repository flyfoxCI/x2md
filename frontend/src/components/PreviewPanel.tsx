import ReactMarkdown from "react-markdown";

import { artifactDownloadUrl } from "../api";
import type { Artifact } from "../types";

interface PreviewPanelProps {
  artifact: Artifact | null;
  markdown: string;
}

export function PreviewPanel({ artifact, markdown }: PreviewPanelProps) {
  return (
    <aside aria-label="Markdown 预览" className="preview-panel">
      <div className="preview-heading">
        <h2>预览</h2>
        {artifact ? (
          <a className="download-link" href={artifactDownloadUrl(artifact.id)}>
            下载 Markdown
          </a>
        ) : null}
      </div>
      <article className="markdown-preview">
        {markdown.trim() ? <ReactMarkdown>{markdown}</ReactMarkdown> : <p className="preview-placeholder">选择来源后，在这里阅读当前 Markdown。</p>}
      </article>
      <section className="assistant-placeholder" aria-label="来源助手将在下一阶段提供">
        <div>
          <strong>来源助手</strong>
          <span>基于当前来源</span>
        </div>
        <p>选择一份来源后，可在下一步对其提问并核对出处。</p>
      </section>
    </aside>
  );
}
