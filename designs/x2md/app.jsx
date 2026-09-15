const { useState, useEffect, useMemo, useRef } = React;

const GENERATED_FALLBACK = {
  translation: [
    "# 中文翻译（自动生成）",
    "",
    "此为演示用的生成结果。真实产品中将基于原文调用 AI 生成全文翻译，并保留原文结构与术语表。",
    "",
    "- 术语表随生成自动维护",
    "- 段落与原文一一对应，便于校对",
  ].join("\n"),
  summary: [
    "# 知识摘要（自动生成）",
    "",
    "- **核心论点**：一句话概括来源的主要主张",
    "- **关键证据**：列出支撑论点的三组事实",
    "- **可复用结论**：沉淀为可检索的结构化知识条目",
  ].join("\n"),
  skill: [
    "---",
    "name: distilled-skill-draft",
    "description: 自动生成的可复用技能草案",
    "---",
    "",
    "# Skill：技能草案",
    "",
    "## 触发条件",
    "当用户询问与该来源相关的方法论时使用。",
    "",
    "## 步骤",
    "1. 提炼来源的核心方法",
    "2. 映射为可执行步骤",
    "3. 标注边界条件与反例",
  ].join("\n"),
  research: [
    "# 深度研究（自动生成）",
    "",
    "- **研究问题**：本来源回答的核心问题是什么",
    "- **证据链**：支撑主张的三组事实与其实验设置",
    "- **反方观点**：来源未覆盖或直接反驳的立场",
    "- **开放问题**：来源没有回答、值得继续追问的点",
    "- **实践启示**：对本知识库后续内容工作的可操作结论",
  ].join("\n"),
};

const VARIANT_THEMES = {
  a: [{ id: "light", label: "浅色", icon: "sun" }, { id: "dark", label: "深色", icon: "moon" }],
  b: [{ id: "warm", label: "暖纸", icon: "sun" }, { id: "cool", label: "冷纸", icon: "moon" }],
  c: [{ id: "obsidian", label: "曜石", icon: "moon" }, { id: "graphite", label: "石墨", icon: "sun" }],
};

function Studio({ variant, label }) {
  const themes = VARIANT_THEMES[variant];
  const [themeId, setThemeId] = useState(themes[0].id);
  const [device, setDevice] = useState("desktop");
  const [sources, setSources] = useState(SOURCES);
  const [selectedId, setSelectedId] = useState(1);
  const [tab, setTab] = useState("translation");
  const [edits, setEdits] = useState({});
  const [generated, setGenerated] = useState({});
  const [saving, setSaving] = useState(false);
  const [deriveBusy, setDeriveBusy] = useState(false);
  const [version, setVersion] = useState(3);
  const [url, setUrl] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogUrl, setDialogUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState(null);
  const [chatDraft, setChatDraft] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const answerIdx = useRef(0);
  const [extraDetails, setExtraDetails] = useState({});
  const [chatMap, setChatMap] = useState(() => {
    const m = {};
    Object.keys(CHAT_SEEDS).forEach((k) => {
      m[k] = CHAT_SEEDS[k].map((t) => Object.assign({}, t));
    });
    return m;
  });

  useEffect(() => {
    if (!toast) return undefined;
    const t = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const selected = sources.find((s) => s.id === selectedId) || sources[0];
  const detail = Object.assign({}, DETAILS[selected.id] || {}, extraDetails[selected.id] || {});
  const genForSource = generated[selected.id] || {};
  let content = null;
  if (tab === "original") content = detail.original || null;
  else content = edits[selected.id + ":" + tab] || detail[tab] || genForSource[tab] || null;
  const canEdit = tab !== "original" && content !== null;

  function selectSource(id) {
    setSelectedId(id);
    const d = Object.assign({}, DETAILS[id] || {}, extraDetails[id] || {});
    setTab(d.translation || (generated[id] || {}).translation ? "translation" : "original");
  }

  function edit(value) {
    const key = selected.id + ":" + tab;
    setEdits((m) => {
      const o = Object.assign({}, m);
      o[key] = value;
      return o;
    });
  }

  function save() {
    if (saving) return;
    setSaving(true);
    window.setTimeout(() => {
      setSaving(false);
      const next = version + 1;
      setVersion(next);
      setToast({ kind: "success", text: "已保存为新版本 v" + next });
    }, 900);
  }

  function derive() {
    if (deriveBusy) return;
    setDeriveBusy(true);
    window.setTimeout(() => {
      setGenerated((g) => {
        const o = Object.assign({}, g);
        o[selected.id] = Object.assign({}, g[selected.id] || {});
        o[selected.id][tab] = GENERATED_FALLBACK[tab];
        return o;
      });
      setDeriveBusy(false);
      setToast({ kind: "success", text: "已生成新的知识版本" });
    }, 1500);
  }

  function sendChat() {
    const q = chatDraft.trim();
    if (!q || chatBusy) return;
    const id = selected.id;
    setChatMap((m) => {
      const o = Object.assign({}, m);
      o[id] = (o[id] || []).concat([{ q: q, pending: true }]);
      return o;
    });
    setChatDraft("");
    setChatBusy(true);
    const ans = CANNED_ANSWERS[answerIdx.current % CANNED_ANSWERS.length];
    answerIdx.current += 1;
    window.setTimeout(() => {
      setChatMap((m) => {
        const o = Object.assign({}, m);
        o[id] = (o[id] || []).map((t) => (t.pending ? { q: t.q, a: ans.a, cites: ans.cites, pending: false } : t));
        return o;
      });
      setChatBusy(false);
    }, 1200);
  }

  function runImport(raw) {
    const u = (raw || "").trim();
    if (!u || importing) return;
    setImporting(true);
    window.setTimeout(() => {
      const isArxiv = /arxiv/.test(u);
      const ns = {
        id: 900 + Math.floor(Math.random() * 90),
        platform: isArxiv ? "arxiv" : "web",
        title: "The Illusion of Thinking — Apple ML Research",
        author: isArxiv ? "Shojaee et al." : null,
        status: "ready",
        updated: "刚刚",
      };
      setExtraDetails((m) => {
        const o = Object.assign({}, m);
        o[ns.id] = {
          original: [
            "# The Illusion of Thinking",
            "",
            "我们提出一个受控谜题环境，用于检验大型推理模型的真实推理边界。",
            "",
            "关键发现：当问题复杂度超过阈值时，模型准确率会**骤降为零**，推理轨迹中出现过早放弃的迹象。",
          ].join("\n"),
          translation: null,
          summary: null,
          skill: null,
        };
        return o;
      });
      setSources((s) => [ns].concat(s.filter((x) => x.id !== ns.id)));
      setImporting(false);
      setUrl("");
      setDialogUrl("");
      setDialogOpen(false);
      setSelectedId(ns.id);
      setTab("original");
      setToast({ kind: "success", text: "来源已导入并保存到知识库" });
    }, 1300);
  }

  const previewHtml = useMemo(() => {
    if (!content) return { __html: '<p class="doc-empty">选择左侧来源并生成内容后，预览将在这里呈现。</p>' };
    return renderMarkdown(content);
  }, [content, edits, generated, tab, selectedId]);

  const chatTurns = chatMap[selected.id] || [];
  const theme = themes.find((t) => t.id === themeId) || themes[0];

  return (
    <div className="stage" data-device={device} data-screen-label={label} data-theme={themeId} data-variant={variant}>
      <HeaderBar
        importing={importing}
        onImport={runImport}
        onOpenDialog={() => setDialogOpen(true)}
        onUrl={setUrl}
        url={url}
      />
      <div className="st-body">
        <Sidebar
          activeId={selected.id}
          onOpenImport={() => setDialogOpen(true)}
          onSelect={selectSource}
          onQuery={setQuery}
          query={query}
          sources={sources}
        />
        <EditorPane
          canEdit={canEdit}
          content={content}
          deriveBusy={deriveBusy}
          onDerive={derive}
          onEdit={edit}
          onSave={save}
          onTab={setTab}
          saving={saving}
          source={selected}
          tab={tab}
          tabs={TABS}
          toast={toast}
        />
        <PreviewPane
          canChat
          chat={chatTurns}
          chatBusy={chatBusy}
          chatDraft={chatDraft}
          device={device}
          html={previewHtml}
          onDevice={setDevice}
          onDraft={setChatDraft}
          onSend={sendChat}
          onTheme={setThemeId}
          theme={theme}
          themes={themes}
        />
      </div>
      <ImportDialog
        busy={importing}
        onClose={() => setDialogOpen(false)}
        onSubmit={runImport}
        onUrl={setDialogUrl}
        open={dialogOpen}
        url={dialogUrl}
      />
    </div>
  );
}

function Frame({ id, tag, title, sub, points, children }) {
  const boxRef = useRef(null);
  const [scale, setScale] = useState(0.62);
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return undefined;
    const update = () => {
      const r = el.getBoundingClientRect();
      const s = Math.min(r.width / 1440, r.height / 860);
      setScale(s > 0 ? s : 0.2);
    };
    update();
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(update);
      ro.observe(el);
      return () => ro.disconnect();
    }
    return undefined;
  }, []);
  function goFullscreen() {
    const el = document.getElementById(id);
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else if (el.requestFullscreen) el.requestFullscreen();
  }
  return (
    <section className="frame" data-screen-label={title} id={id}>
      <header className="frame-head">
        <span className="frame-tag">{tag}</span>
        <div className="frame-title">
          <h3>{title}</h3>
          <p>{sub}</p>
        </div>
        <button className="frame-full" onClick={goFullscreen} type="button"><Icon name="monitor" size={13} />全屏预览</button>
      </header>
      <div className="frame-box" ref={boxRef}>
        <div className="frame-stage" style={{ width: "1440px", height: "860px", transform: "scale(" + scale + ")" }}>
          {children}
        </div>
      </div>
      <ul className="frame-points">
        {points.map((p, i) => <li key={i}>{p}</li>)}
      </ul>
    </section>
  );
}

const LAYER_NOTES = [
  {
    n: "01", title: "视觉层", body: "重校色板与层级：确立 ink / muted / faint 三级文字、面板与画布两层底色；引入统一的圆角（8/12/16）与三级阴影；主按钮改用纵向渐变 + 悬停浮起，链接与焦点环统一使用品牌色。",
  },
  {
    n: "02", title: "布局层", body: "三栏宽度重排（272 / 自适应 / 408），以 1px 发丝线 + 背景色差分区取代重边框；顶栏按「导航 · 品牌 · 导入 · 状态」重新分组；预览面板新增主题与设备控制组。",
  },
  {
    n: "03", title: "交互层", body: "全部可点元素获得 hover / focus-visible 态；标签页滑入式下划线；按钮悬停轻微上浮；导入对话框缩放淡入；聊天回答为气泡 + 思考点动画；保存与生成以顶部 toast 反馈。",
  },
  {
    n: "04", title: "组件层", body: "来源行增加平台彩色徽标与状态胶囊；标签页带图标与滑动指示条；编辑器保留行号槽并等宽对齐；预览排版建立 h1-h3 / 引文 / 代码块 / 表格的完整样式；空状态与生成态卡片化。",
  },
];

function Review() {
  return (
    <div className="review">
      <header className="review-hero">
        <p className="review-kicker">X² Studio · Expert Content Knowledge Base</p>
        <h1>UI 高级化设计提案</h1>
        <p className="review-lede">
          基于 x2md 现有前端代码（React 19 + 手写 CSS token）的真实结构改写：保留产品骨架与信息架构，
          从视觉、布局、交互、组件四个层面给出三个差异化方向。每个方向均可交互——切换标签页、发起聊天、
          保存版本、打开导入对话框、切换主题与设备预览。
        </p>
        <div className="review-chips">
          <span>设计上下文：frontend/src 源码（tokens / app / workspace.css + 7 个组件）</span>
          <span>保真度：Hi-Fi 交互原型</span>
          <span>内容：与真实信息架构一致的模拟数据</span>
        </div>
      </header>

      <section aria-label="设计说明" className="review-notes">
        <h2>四个层面的升级逻辑</h2>
        <div className="review-notes-grid">
          {LAYER_NOTES.map((n) => (
            <article className="note-card" key={n.n}>
              <span className="note-num">{n.n}</span>
              <h3>{n.title}</h3>
              <p>{n.body}</p>
            </article>
          ))}
        </div>
      </section>

      <Frame
        id="frame-a"
        points={[
          "沿用海洋色系但重校层次：深空侧栏 + 高对比主按钮 + 呼吸感留白",
          "标签页滑动指示条、状态 LED 脉冲、按钮悬停浮起等微交互",
          "预览排版完整化：代码块带窗口栏、表格圆角化、引用块着色",
        ]}
        sub="Refined Ocean — 现有基因的克制升级，最贴近当前实现"
        tag="方向 A"
        title="精修海洋 · 专业工具感"
      >
        <Studio label="方向 A · 精修海洋" variant="a" />
      </Frame>

      <Frame
        id="frame-b"
        points={[
          "暖纸色板 + 衬线展示字体，阅读器气质；侧栏由深色改为暖纸浅色",
          "大圆角、暖色阴影、更松弛的行距与留白节奏",
          "预览区呈现为居中文档页，强调「沉下来的知识」",
        ]}
        sub="Paper Studio — 明亮纸感编辑器，阅读与沉淀优先"
        tag="方向 B"
        title="纸感书房 · 沉淀知识"
      >
        <Studio label="方向 B · 纸感书房" variant="b" />
      </Frame>

      <Frame
        id="frame-c"
        points={[
          "深色优先：石墨蓝黑底、玻璃面板、发丝级描边",
          "电光青→靛蓝渐变主行动点，焦点带辉光；标签与版本号使用等宽字体",
          "面板间以间隙悬浮，弱化边框、强化层叠",
        ]}
        sub="Midnight Studio — 深色代码工具气质，开发者向"
        tag="方向 C"
        title="午夜工作室 · 玻璃与辉光"
      >
        <Studio label="方向 C · 午夜工作室" variant="c" />
      </Frame>

      <footer className="review-next">
        <h2>建议的下一步</h2>
        <ol>
          <li>选定一个方向（或在方向间点选混搭元素），我会把它细化为完整的 tokens + 组件规范；</li>
          <li>确认后可将定稿映射回 <code>frontend/src/styles/tokens.css</code> 与组件样式，保持现有 DOM 与测试不破坏；</li>
          <li>移动端断点（720px / 1120px）在定稿方向上单独过一遍。</li>
        </ol>
      </footer>
    </div>
  );
}

const rootEl = document.getElementById("root");
ReactDOM.createRoot(rootEl).render(<Review />);
