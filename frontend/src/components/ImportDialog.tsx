import { useEffect, useRef, useState, type KeyboardEvent } from "react";

interface ImportDialogProps {
  open: boolean;
  importing: boolean;
  onClose: () => void;
  onImport: (url: string) => void;
}

export function ImportDialog({ open, importing, onClose, onImport }: ImportDialogProps) {
  const [url, setUrl] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    }
  }, [open]);

  if (!open) {
    return null;
  }

  function trapFocus(event: KeyboardEvent<HTMLFormElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") {
      return;
    }
    const focusable = Array.from(
      formRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), [href], select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])",
      ) ?? [],
    );
    const first = focusable.at(0);
    const last = focusable.at(-1);
    if (!first || !last) {
      return;
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <div aria-labelledby="import-dialog-title" aria-modal="true" className="dialog-scrim" role="dialog">
      <form
        className="import-dialog"
        onKeyDown={trapFocus}
        onSubmit={(event) => {
          event.preventDefault();
          onImport(url);
        }}
        ref={formRef}
      >
        <div className="dialog-heading">
          <div>
            <h2 id="import-dialog-title">导入专家来源</h2>
            <p>仅抓取可公开访问的 HTTPS 页面与平台内容。</p>
          </div>
          <button aria-label="关闭导入对话框" className="icon-button" onClick={onClose} type="button">×</button>
        </div>
        <label htmlFor="dialog-source-url">来源链接</label>
        <input
          id="dialog-source-url"
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://github.com/…"
          ref={inputRef}
          type="url"
          value={url}
        />
        <div className="dialog-actions">
          <button className="secondary-button" onClick={onClose} type="button">取消</button>
          <button className="primary-button" disabled={importing || !url.trim()} type="submit">
            {importing ? "导入中…" : "导入来源"}
          </button>
        </div>
      </form>
    </div>
  );
}
