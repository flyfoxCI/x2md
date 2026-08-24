import { useState, type FormEvent, type RefObject } from "react";

import type { AuthenticatedUser } from "../types";

interface AppHeaderProps {
  url: string;
  importing: boolean;
  onUrlChange: (url: string) => void;
  onImport: () => void;
  onOpenLibrary: (trigger: HTMLButtonElement) => void;
  libraryButtonRef: RefObject<HTMLButtonElement | null>;
  user: AuthenticatedUser;
  onOpenAccount: (trigger: HTMLButtonElement) => void;
  onLogout: () => Promise<void>;
}

export function AppHeader({
  url,
  importing,
  onUrlChange,
  onImport,
  onOpenLibrary,
  libraryButtonRef,
  user,
  onOpenAccount,
  onLogout,
}: AppHeaderProps) {
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onImport();
  }

  async function logOut() {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await onLogout();
    } catch {
      setLogoutError("退出登录失败，请稍后重试。");
    } finally {
      setLoggingOut(false);
    }
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
      <div className="header-account-actions">
        <button
          className="account-button"
          onClick={(event) => onOpenAccount(event.currentTarget)}
          type="button"
        >
          账户：{user.username}
        </button>
        <button
          aria-label="退出登录"
          className="secondary-button header-logout-button"
          disabled={loggingOut}
          onClick={() => void logOut()}
          type="button"
        >
          {loggingOut ? "退出中…" : "退出"}
        </button>
        {logoutError ? <p className="header-logout-error" role="alert">{logoutError}</p> : null}
      </div>
    </header>
  );
}
