const { useRef } = React;

const TABS = [
  { id: "original", label: "原文", icon: "file" },
  { id: "translation", label: "中文翻译", icon: "lang" },
  { id: "summary", label: "知识摘要", icon: "list" },
  { id: "skill", label: "Distilled Skill", icon: "sparkle" },
  { id: "research", label: "深度研究", icon: "compass" },
];

const FENCE = String.fromCharCode(96).repeat(3);

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inlineMd(s) {
  s = escapeHtml(s);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(new RegExp(String.fromCharCode(96) + "([^" + String.fromCharCode(96) + "\\n]+)" + String.fromCharCode(96), "g"), "<code>$1</code>");
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return s;
}

function renderMarkdown(md) {
  const lines = md.split("\n");
  const out = [];
  let i = 0;
  if (lines[0] === "---") {
    let end = -1;
    for (let j = 1; j < lines.length; j++) { if (lines[j] === "---") { end = j; break; } }
    if (end > 0) {
      const items = [];
      for (let j = 1; j < end; j++) {
        const m = lines[j].match(/^([a-z-]+):\s*(.*)$/);
        if (m) items.push('<span class="doc-meta-item"><b>' + m[1] + "</b>" + inlineMd(m[2]) + "</span>");
      }
      out.push('<div class="doc-meta">' + items.join("") + "</div>");
      i = end + 1;
    }
  }
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") { i++; continue; }
    if (line.startsWith("###")) { out.push("<h3>" + inlineMd(line.slice(4)) + "</h3>"); i++; continue; }
    if (line.startsWith("##")) { out.push("<h2>" + inlineMd(line.replace(/^##\s+/, "")) + "</h2>"); i++; continue; }
    if (line.startsWith("#")) { out.push("<h1>" + inlineMd(line.replace(/^#\s+/, "")) + "</h1>"); i++; continue; }
    if (line.startsWith(FENCE)) {
      const lang = line.slice(3).trim();
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith(FENCE)) { buf.push(lines[i]); i++; }
      i++;
      out.push('<div class="doc-code"><div class="doc-code-bar"><i></i><i></i><i></i><span>' + (lang || "code") + '</span></div><pre><code>' + escapeHtml(buf.join("\n")) + "</code></pre></div>");
      continue;
    }
    if (line.startsWith("> ")) {
      const buf = [];
      while (i < lines.length && lines[i].startsWith("> ")) { buf.push(lines[i].slice(2)); i++; }
      out.push("<blockquote>" + buf.map(inlineMd).join("<br/>") + "</blockquote>");
      continue;
    }
    if (line.indexOf("| ") === 0) {
      const rows = [];
      while (i < lines.length && lines[i].charAt(0) === "|") { rows.push(lines[i]); i++; }
      const cellsOf = (r) => r.split("|").slice(1, -1).map((c) => c.trim());
      const head = cellsOf(rows[0]);
      const body = rows.slice(2).map(cellsOf);
      out.push("<table><thead><tr>" + head.map((c) => "<th>" + inlineMd(c) + "</th>").join("") + "</tr></thead><tbody>" + body.map((r) => "<tr>" + r.map((c) => "<td>" + inlineMd(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
      continue;
    }
    if (/^- /.test(line)) {
      const buf = [];
      while (i < lines.length && /^- /.test(lines[i])) { buf.push("<li>" + inlineMd(lines[i].slice(2)) + "</li>"); i++; }
      out.push("<ul>" + buf.join("") + "</ul>");
      continue;
    }
    if (/^\\d+\\. /.test(line)) {
      const buf = [];
      while (i < lines.length && /^\d+\. /.test(lines[i])) { buf.push("<li>" + inlineMd(lines[i].replace(/^\d+\. /, "")) + "</li>"); i++; }
      out.push("<ol>" + buf.join("") + "</ol>");
      continue;
    }
    if (/^---+$/.test(line.trim())) { out.push("<hr/>"); i++; continue; }
    out.push("<p>" + inlineMd(line) + "</p>");
    i++;
  }
  return { __html: out.join("\n") };
}

function HeaderBar({ url, onUrl, onImport, importing, onOpenDialog }) {
  return (
    <header className="st-header">
      <span aria-hidden="true" className="st-logo">X²</span>
      <div className="st-brand">
        <b>X² Studio</b>
        <span>专家内容知识库</span>
      </div>
      <form className="st-import" onSubmit={(e) => { e.preventDefault(); onImport(url); }}>
        <span className="st-import-field">
          <Icon name="link" size={14} />
          <input
            onChange={(e) => onUrl(e.target.value)}
            placeholder="粘贴 X、GitHub、YouTube、arXiv、Hugging Face 或网页链接"
            type="url"
            value={url}
          />
        </span>
        <button className="btn btn-primary" disabled={importing || !url.trim()} type="submit">
          {importing ? "导入中…" : "导入"}
        </button>
      </form>
      <div className="st-header-right">
        <button aria-label="导入新来源" className="st-icon-btn" onClick={onOpenDialog} type="button">
          <Icon name="plus" size={16} />
        </button>
        <span className="st-status"><span aria-hidden="true" className="led" />来源已导入 · 可生成</span>
      </div>
    </header>
  );
}

function Sidebar({ sources, activeId, onSelect, onOpenImport, query, onQuery }) {
  const q = query.trim().toLowerCase();
  const shown = q ? sources.filter((s) => (s.title + " " + (s.author || "")).toLowerCase().indexOf(q) !== -1) : sources;
  const skills = sources.filter((s) => s.status === "ready").length;
  return (
    <aside className="st-sidebar" data-screen-label="知识库侧栏">
      <div className="ss-head">
        <div className="ss-title">
          <Icon name="library" size={17} strokeWidth={1.8} />
          <h2>知识库</h2>
          <span className="ss-count">{sources.length}</span>
        </div>
        <div className="ss-actions">
          <button aria-label="导入新来源" className="st-icon-btn" onClick={onOpenImport} type="button">
            <Icon name="plus" size={16} />
          </button>
        </div>
      </div>
      <label className="ss-search">
        <Icon name="search" size={14} />
        <input onChange={(e) => onQuery(e.target.value)} placeholder="搜索知识库…" type="search" value={query} />
      </label>
      <nav aria-label="知识库筛选" className="ss-nav">
        <button className="is-active" type="button"><span>全部来源</span><strong>{sources.length}</strong></button>
        <button type="button"><span>最近导入</span></button>
        <button type="button"><span>我的 Skill</span><strong>{skills}</strong></button>
      </nav>
      <div className="ss-listhead">来源列表</div>
      <div className="ss-list">
        {shown.map((s) => (
          <button
            className={"ss-row" + (s.id === activeId ? " is-active" : "")}
            key={s.id}
            onClick={() => onSelect(s.id)}
            type="button"
          >
            <PlatformChip platform={s.platform} size={26} />
            <span className="ss-copy">
              <strong>{s.title}</strong>
              <span>{platformLabels[s.platform]}{s.author ? " · " + s.author : ""}</span>
              {s.status !== "ready" ? <em className={"tag tag-" + s.status}>{s.status === "partial" ? "部分导入" : "已受限"}</em> : null}
            </span>
            <span aria-hidden="true" className="ss-more"><Icon name="dots" size={14} /></span>
          </button>
        ))}
        {shown.length === 0 ? <p className="ss-muted">没有匹配「{query}」的来源。</p> : null}
      </div>
      <div className="ss-foot"><span aria-hidden="true" className="led" />同步完成 · {skills} / {sources.length} 可生成</div>
    </aside>
  );
}

function EditorPane({ source, tab, tabs, content, canEdit, saving, onSave, onEdit, onTab, deriveBusy, onDerive, toast }) {
  const taRef = useRef(null);
  const gutterRef = useRef(null);
  const lines = content ? content.split("\n") : [];
  const activeDef = tabs.find((t) => t.id === tab);

  function syncScroll() {
    if (taRef.current && gutterRef.current) {
      gutterRef.current.style.transform = "translateY(-" + taRef.current.scrollTop + "px)";
    }
  }

  return (
    <section className="st-editor" data-screen-label="内容工作区">
      {toast ? (
        <div className={"st-toast st-toast-" + toast.kind} role="status">
          <Icon name={toast.kind === "success" ? "check" : "alert"} size={14} strokeWidth={2.2} />
          <span>{toast.text}</span>
        </div>
      ) : null}
      <div className="se-prov">
        <PlatformChip platform={source.platform} size={30} />
        <div className="se-prov-copy">
          <h2>{source.title}</h2>
          <p>
            {platformLabels[source.platform]}{source.author ? " · " + source.author : ""}
            {" · "}
            <a href="#" onClick={(e) => e.preventDefault()}>查看原始来源 <Icon name="external" size={10} /></a>
          </p>
        </div>
        <span className="se-ver">{"v3 · " + source.updated}</span>
      </div>
      <div aria-label="内容视图" className="se-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            aria-selected={tab === t.id}
            className={tab === t.id ? "is-active" : ""}
            key={t.id}
            onClick={() => onTab(t.id)}
            role="tab"
            type="button"
          >
            <Icon className="tab-ico" name={t.icon} size={14} />
            {t.label}
          </button>
        ))}
      </div>
      <div className="se-toolbar">
        <span className="se-label"><Icon name={activeDef.icon} size={13} />{activeDef.label}</span>
        <div className="se-tools">
          {canEdit ? (
            <button className="btn btn-primary" disabled={saving} onClick={onSave} type="button">
              {saving ? "保存中…" : "保存版本"}
            </button>
          ) : (
            <span className="se-readonly"><Icon name="book" size={13} />原始来源保持只读</span>
          )}
        </div>
      </div>
      {content === null ? (
        <div className="se-derive">
          <div className="se-derive-card">
            <span className="se-derive-icon"><Icon name="sparkle" size={22} /></span>
            <h3>{activeDef.label}尚未生成</h3>
            <p>基于原文一键生成，生成后可继续编辑为你的知识版本。</p>
            <button className="btn btn-primary" disabled={deriveBusy} onClick={onDerive} type="button">
              <Icon name="zap" size={14} />{deriveBusy ? "正在生成…" : "生成" + activeDef.label}
            </button>
          </div>
        </div>
      ) : (
        <div className="se-body">
          <div aria-hidden="true" className="se-gutter">
            <div className="se-gutter-in" ref={gutterRef}>
              {Array.from({ length: lines.length }, (_, n) => <span key={n}>{n + 1}</span>)}
            </div>
          </div>
          <textarea
            aria-label="Markdown 内容"
            onChange={(e) => onEdit(e.target.value)}
            onScroll={syncScroll}
            readOnly={tab === "original"}
            spellCheck={false}
            value={content}
            wrap="off"
          />
        </div>
      )}
      <footer className="se-foot">
        <span>{(content ? content.length : 0).toLocaleString()} 字符 · {lines.length} 行</span>
        <span>{tab === "original" ? "原始来源保持不变" : "编辑会保存为新版本"}</span>
      </footer>
    </section>
  );
}

function PreviewPane({ html, device, onDevice, theme, themes, onTheme, chat, chatDraft, onDraft, onSend, chatBusy, canChat }) {
  const listRef = useRef(null);
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [chat, chatBusy]);

  return (
    <aside className="st-preview" data-screen-label="预览面板">
      <div className="sp-head">
        <h2>预览</h2>
        <div className="sp-actions">
          <label className="sp-theme">
            <Icon name={theme.icon} size={13} />
            <select aria-label="界面主题" onChange={(e) => onTheme(e.target.value)} value={theme.id}>
              {themes.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <div aria-label="预览设备" className="sp-device" role="group">
            <button aria-pressed={device === "desktop"} onClick={() => onDevice("desktop")} type="button"><Icon name="monitor" size={12} />桌面</button>
            <button aria-pressed={device === "mobile"} onClick={() => onDevice("mobile")} type="button"><Icon name="phone" size={12} />手机</button>
          </div>
          <a className="sp-download" href="#" onClick={(e) => e.preventDefault()}><Icon name="download" size={13} />Markdown</a>
        </div>
      </div>
      <div className="sp-scroll">
        <div className="sp-frame">
          <article className="doc" dangerouslySetInnerHTML={html} />
        </div>
      </div>
      <section aria-label="来源助手" className="st-chat">
        <div className="sc-head">
          <span className="sc-badge"><Icon name="sparkle" size={14} /></span>
          <div>
            <h3>来源助手</h3>
            <p>仅依据当前来源与其知识版本回答</p>
          </div>
        </div>
        <div className="sc-list" ref={listRef}>
          {chat.length === 0 && !chatBusy ? <p className="sc-empty">向当前来源提问，例如「这个方法适合什么场景？」</p> : null}
          {chat.map((t, idx) => (
            <div className="sc-turn" key={idx}>
              <p className="sc-q">{t.q}</p>
              {t.pending ? (
                <p aria-label="回答中" className="sc-thinking"><span /><span /><span /></p>
              ) : (
                <div className="sc-a" dangerouslySetInnerHTML={renderMarkdown(t.a)} />
              )}
              {t.cites && !t.pending ? (
                <div className="sc-cites">
                  {t.cites.map((c, ci) => <span className="sc-cite" key={ci}><Icon name="external" size={10} />{c}</span>)}
                </div>
              ) : null}
            </div>
          ))}
        </div>
        <form className="sc-form" onSubmit={(e) => { e.preventDefault(); onSend(); }}>
          <textarea
            disabled={!canChat || chatBusy}
            onChange={(e) => onDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            placeholder={canChat ? "针对当前来源提问…" : "选择来源后即可提问"}
            rows={1}
            value={chatDraft}
          />
          <button aria-label="发送问题" className="btn btn-primary sc-send" disabled={!canChat || chatBusy || !chatDraft.trim()} type="submit">
            <Icon name="send" size={14} />
          </button>
        </form>
      </section>
    </aside>
  );
}

function ImportDialog({ open, onClose, onSubmit, busy, url, onUrl }) {
  if (!open) return null;
  return (
    <div className="st-dialog" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} role="presentation">
      <form aria-labelledby="sd-title" className="sd" onSubmit={(e) => { e.preventDefault(); onSubmit(url); }} role="dialog">
        <div className="sd-head">
          <div>
            <h2 id="sd-title">导入专家来源</h2>
            <p>仅抓取可公开访问的 HTTPS 页面与平台内容。</p>
          </div>
          <button aria-label="关闭" className="st-icon-btn" onClick={onClose} type="button"><Icon name="close" size={15} /></button>
        </div>
        <div className="sd-plats">
          {["x", "github", "youtube", "youtube", "web"].map((p, idx) => (
            <span className="sd-plat" key={idx}><PlatformChip platform={p} size={15} />{platformLabels[p]}</span>
          ))}
        </div>
        <label className="sd-label" htmlFor="sd-url">来源链接</label>
        <div className="sd-field">
          <Icon name="link" size={14} />
          <input autoFocus id="sd-url" onChange={(e) => onUrl(e.target.value)} placeholder="https://arxiv.org/abs/1706.03762" type="url" value={url} />
        </div>
        <div className="sd-actions">
          <button className="btn btn-ghost" onClick={onClose} type="button">取消</button>
          <button className="btn btn-primary" disabled={busy || !url.trim()} type="submit">{busy ? "导入中…" : "导入来源"}</button>
        </div>
      </form>
    </div>
  );
}

Object.assign(window, { TABS, renderMarkdown, HeaderBar, Sidebar, EditorPane, PreviewPane, ImportDialog });
