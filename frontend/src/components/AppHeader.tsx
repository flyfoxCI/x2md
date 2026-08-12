import type { FormEvent, RefObject } from "react";

interface AppHeaderProps {
  url: string;
  importing: boolean;
  onUrlChange: (url: string) => void;
  onImport: () => void;
  onOpenLibrary: (trigger: HTMLButtonElement) => void;
  libraryButtonRef: RefObject<HTMLButtonElement | null>;
}

export function AppHeader({
  url,
  importing,
  onUrlChange,
  onImport,
  onOpenLibrary,
  libraryButtonRef,
}: AppHeaderProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onImport();
  }

  return (
    <header className="app-header">
      <button
        aria-label="打开知识库"
        className="library-menu-button"
        onClick={(event) => onOpenLibrary(event.currentTarget)}
        ref={libraryButtonRef}
        type="button"
      >
        <span aria-hidden="true">☰</span>
      </button>
      <div className="brand-lockup">
        <h1>X² Studio</h1>
        <span>专家内容知识库</span>
      </div>
      <form className="import-bar" onSubmit={submit}>
        <label className="sr-only" htmlFor="source-url">导入来源链接</label>
        <input
          aria-describedby="source-url-help"
          id="source-url"
          onChange={(event) => onUrlChange(event.target.value)}
          placeholder="粘贴 X、GitHub、YouTube、arXiv、Hugging Face 或网页链接"
          type="url"
          value={url}
        />
        <span className="sr-only" id="source-url-help">仅导入公开 HTTPS 链接。</span>
        <button className="primary-button import-button" disabled={importing || !url.trim()} type="submit">
          {importing ? "导入中…" : "导入"}
        </button>
      </form>
      <div aria-label="服务状态" className="header-status">
        <span aria-hidden="true" className="status-dot" />
        <span>来源已导入 · 可生成</span>
      </div>
    </header>
  );
}
