import { SafeMarkdown } from "./SafeMarkdown";

interface MarkdownPreviewProps {
  markdown: string;
}

export function MarkdownPreview({ markdown }: MarkdownPreviewProps) {
  if (!markdown.trim()) {
    return <p className="preview-placeholder">选择来源后，在这里阅读当前 Markdown。</p>;
  }

  return <SafeMarkdown>{markdown}</SafeMarkdown>;
}
