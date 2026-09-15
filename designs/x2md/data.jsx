// Mock data —— 结构镜像 frontend/src/types.ts（Source / Artifact / ChatTurn）
const BT = String.fromCharCode(96);
const F = BT + BT + BT; // markdown 代码围栏

const platformLabels = {
  arxiv: "arXiv", github: "GitHub", huggingface: "Hugging Face",
  web: "网页", x: "X", youtube: "YouTube",
};

const SOURCES = [
  { id: 1, platform: "arxiv", title: "Attention Is All You Need", author: "Vaswani et al.", status: "ready", updated: "2 小时前" },
  { id: 2, platform: "github", title: "fastapi / fastapi — 现代高性能 Web 框架", author: "tiangolo", status: "ready", updated: "昨天" },
  { id: 3, platform: "youtube", title: "Let’s build GPT（视频笔记）", author: "Andrej Karpathy", status: "ready", updated: "3 天前" },
  { id: 4, platform: "x", title: "关于规模法则与最优算力的线程", author: "@karpathy", status: "ready", updated: "5 天前" },
  { id: 5, platform: "huggingface", title: "deepseek-ai / DeepSeek-R1", author: "deepseek-ai", status: "ready", updated: "上周" },
  { id: 6, platform: "web", title: "The Bitter Lesson（苦涩的教训）", author: "Rich Sutton", status: "ready", updated: "上周" },
  { id: 7, platform: "web", title: "DDIA 第 9 章阅读笔记：一致性与共识", author: "Martin Kleppmann", status: "partial", updated: "2 周前" },
  { id: 8, platform: "github", title: "pallets / flask — 轻量 WSGI 框架", author: "pallets", status: "blocked", updated: "3 周前" },
];

const DETAILS = {
  1: {
    original: [
      "# Attention Is All You Need",
      "",
      "We propose a new simple network architecture, the **Transformer**, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely."
    ].join("\n"),
    translation: [
      "# 注意力就是你所需要的一切",
      "",
      "> 原文：Vaswani et al., *Attention Is All You Need*, NeurIPS 2017 · [arxiv.org/abs/1706.03762](https://arxiv.org/abs/1706.03762)",
      "",
      "## 摘要",
      "",
      "主导性的序列转导模型建立在复杂的循环或卷积神经网络之上。我们提出 **Transformer**——一种完全依赖注意力机制、彻底摒弃循环与卷积的新架构。",
      "",
      "## 1 引言",
      "",
      "- RNN、LSTM 与 GRU 的计算本质是**顺序**的，样本内无法并行",
      "- 注意力机制移除了这一约束：所有位置**同时计算**",
      "- 在 WMT 2014 英→德任务上达到 **28.4 BLEU**，领先此前最佳结果超过 2 BLEU",
      "",
      "## 3.2 缩放点积注意力",
      "",
      "输入由查询 Q、键 K 与值 V 构成，注意力按以下方式计算：",
      "",
      F + "python",
      "def attention(Q, K, V):",
      "    d_k = K.shape[-1]",
      "    scores = softmax(Q @ K.transpose(-2, -1) / d_k ** 0.5)",
      "    return scores @ V",
      F,
      "",
      "| 模型 | 训练成本（FLOPs） | BLEU |",
      "| --- | --- | --- |",
      "| ByteNet | — | 27.3 |",
      "| Transformer（base） | 3.3×10¹⁸ | 27.3 |",
      "| **Transformer（big）** | 2.3×10¹⁹ | **28.4** |",
      "",
      "> **为什么除以 √d_k？** 当 d_k 较大时，点积的量级随之增大，会把 softmax 推入梯度极小的饱和区；缩放因子维持了梯度稳定。",
      "",
      "## 6 实验结果",
      "",
      "1. Transformer 以更低的训练成本超越了此前发表的所有单模型",
      "2. 仅用位置编码即可较好地泛化到更长的序列",
      "3. 注意力权重可视化表明：模型确实学到了句法结构与指代关系"
    ].join("\n"),
    summary: [
      "# 知识摘要：Transformer",
      "",
      "## 一句话",
      "以**自注意力取代递归**：每个位置并行地对全部位置做加权聚合，训练效率与长程依赖同时受益。",
      "",
      "## 要点",
      "",
      "- **复杂度**：O(n²·d)，序列长度的平方，但完全可并行",
      "- **三角色**：Query / Key / Value 由三个可学习投影矩阵生成",
      "- **多头**：8 个头并行关注不同的表示子空间",
      "- **位置**：自注意力对排列不变，需以正弦位置编码注入顺序",
      "",
      "## 适用场景",
      "",
      "| 场景 | 契合度 |",
      "| --- | --- |",
      "| 长文档理解 | 高（并行优势） |",
      "| 流式实时推理 | 中（需 KV 缓存） |",
      "| 端侧极小设备 | 低（参数量大） |"
    ].join("\n"),
    skill: [
      "---",
      "name: transformer-explainer",
      "description: 用类比与 10 行代码向工程师讲清自注意力机制",
      "---",
      "",
      "# Skill：Transformer 高效讲解",
      "",
      "## 步骤",
      "",
      "1. 以「逐词处理」对比「一次看全句」开场",
      "2. 用图书馆检索的类比解释 Q / K / V 三种角色",
      "3. 给出不超过 10 行的极简 attention 实现（NumPy）",
      "4. 以 WMT 14 的 28.4 BLEU 数据作为效果证据收尾",
      "",
      "## 边界",
      "",
      "- 不展开 BERT / GPT 等衍生架构",
      "- 默认听众具备基础机器学习背景"
    ].join("\n"),
    research: [
      "---",
      "research-question: 自注意力为何能取代递归成为序列建模主干？",
      "confidence: 高（原文论证 + 实验数据双重支撑）",
      "---",
      "",
      "# 深度研究：Transformer 的方法论意义",
      "",
      "## 1 研究问题",
      "",
      "递归结构的顺序瓶颈是否可以被「全并行 + 注意力」替代，并在翻译质量上同时占优？",
      "",
      "## 2 证据链",
      "",
      "- **质量证据**：WMT 14 英→德 28.4 BLEU，超过此前最佳 2 BLEU 以上",
      "- **效率证据**：base 模型训练成本 3.3×10¹⁸ FLOPs，低于同期竞争者",
      "- **机制证据**：注意力可视化显示模型学到句法与指代结构",
      "",
      "## 3 反方观点与边界",
      "",
      "> O(n²) 注意力矩阵在超长序列上的成本不可忽略——这是后来稀疏注意力研究的直接动机。",
      "",
      "## 4 开放问题",
      "",
      "1. 注意力能否严格证明比递归更具表达力，还是只在数据规模上占优？",
      "2. 位置编码的归纳偏置在何种长度上开始失效？",
      "",
      "## 5 对知识库的启示",
      "",
      "- 专家内容的价值在于**可被检索与组合**，本来源应优先沉淀机制类摘要而非全文翻译",
    ].join("\n")
  },
  2: {
    original: [
      "# FastAPI",
      "",
      "FastAPI 是一个用于构建 API 的现代、快速（高性能）Web 框架，基于标准 Python 类型提示。",
      "",
      F + "python",
      "from fastapi import FastAPI",
      "",
      "app = FastAPI()",
      "",
      "@app.get(\"/items/{item_id}\")",
      "def read_item(item_id: int, q: str | None = None):",
      "    return {\"item_id\": item_id, \"q\": q}",
      F,
      "",
      "**关键特性**：自动生成交互式文档（OpenAPI）、类型提示即数据校验、原生 async 支持。"
    ].join("\n"),
    translation: null,
    summary: [
      "# 知识摘要：FastAPI",
      "",
      "- **定位**：Python 生态的高性能异步 Web 框架，构建于 Starlette 与 Pydantic 之上",
      "- **核心卖点**：类型提示即接口契约；自动生成 OpenAPI 交互文档",
      "- **适用**：API 服务、微服务、ML 模型在线服务"
    ].join("\n"),
    skill: null
  },
  3: {
    original: [
      "# Let’s build GPT（视频笔记）",
      "",
      "- 00:00 Bigram 模型与最简语言模型",
      "- 12:40 单头自注意力：加权聚合与因果掩码",
      "- 31:05 多头注意力 = 并行的子空间通信",
      "- 1:02:00 前馈层与残差连接、LayerNorm",
      "",
      "核心洞见：attention 是**通信机制**，feed-forward 是**计算机制**，二者交替堆叠。"
    ].join("\n"),
    translation: null,
    summary: [
      "# 知识摘要：从零构建 GPT",
      "",
      "1. 先跑通 bigram 基线，再逐层加码：embedding → 注意力 → 前馈 → 残差",
      "2. 训练稳定性三件套：LayerNorm、残差连接、学习率预热",
      "3. 最值得回看的片段：12:40（单头注意力）与 1:02:00（FFN + 残差）"
    ].join("\n"),
    skill: null
  },
  4: {
    original: [
      "# 规模法则（scaling laws）线程要点",
      "",
      "1. 算力、数据、参数三者的幂律关系，是可预测的投资曲线",
      "2. Chinchilla 修正：同等算力预算下，数据与参数应**等比**放大",
      "3. 部署侧的新瓶颈：推理成本正在超过训练成本"
    ].join("\n"),
    translation: null,
    summary: null,
    skill: null
  },
  5: {
    original: [
      "# DeepSeek-R1",
      "",
      "We introduce our first-generation reasoning models, trained via large-scale reinforcement learning with verifiable rewards."
    ].join("\n"),
    translation: [
      "# DeepSeek-R1（翻译）",
      "",
      "我们推出第一代推理模型：以**可验证奖励的大规模强化学习**直接训练推理能力。",
      "",
      "- **R1-Zero**：纯强化学习、无监督冷启动，涌现出自我验证与反思行为",
      "- **R1**：冷启动数据 + 多阶段训练，可读性显著提升",
      "- **蒸馏系**：将推理能力下沉到 1.5B–70B 的稠密模型"
    ].join("\n"),
    summary: null,
    skill: null
  },
  6: {
    original: [
      "# The Bitter Lesson",
      "",
      "The biggest lesson from 70 years of AI research is that general methods that leverage computation are ultimately the most effective…"
    ].join("\n"),
    translation: [
      "# 苦涩的教训（翻译）",
      "",
      "> 七十年 AI 研究最大的教训：**依赖算力的通用方法**，终将大幅胜过依赖人类知识注入的方法。",
      "",
      "- 搜索与学习，是唯二能随算力无限扩展的技术",
      "- 对内容工作的启示：沉淀可检索、可生成的知识资产，而非一次性精修文本"
    ].join("\n"),
    summary: [
      "# 知识摘要：The Bitter Lesson",
      "",
      "**核心论点**：人类先验是短期捷径、长期枷锁；算力 + 通用方法才是主线。",
      "",
      "- 证据链：深蓝 → 自我对弈 → 自监督预训练",
      "- 启示：把专家内容做成可检索、可生成的知识库，而非手工精修的一次性文本"
    ].join("\n"),
    skill: null
  },
  7: {
    original: [
      "# DDIA 第 9 章：一致性与共识（节选）",
      "",
      "线性一致性：一旦写入完成，所有后续读取都能读到该值……",
      "CAP 的准确含义：网络分区发生时，只能在一致性与可用性之间二选一。"
    ].join("\n"),
    translation: null,
    summary: [
      "# 知识摘要：一致性与共识",
      "",
      "- 线性一致性 = **新鲜度**保证；可串行化 = **事务次序**保证，两者正交",
      "- 分区是必然事件，取舍只在分区发生的那一刻生效"
    ].join("\n"),
    skill: null
  },
  8: {
    original: "（该来源为付费墙内容，仅元数据可用。导入已受限，无法生成知识版本。）",
    translation: null,
    summary: null,
    skill: null
  },
};

const CHAT_SEEDS = {
  1: [{
    q: "自注意力相比 RNN 的核心优势是什么？",
    a: [
      "两点最关键：",
      "",
      "1. **并行度**——RNN 必须逐时间步计算，注意力一次看全序列，训练吞吐高一个数量级；",
      "2. **路径长度**——任意两个位置一步直达，长程依赖的学习难度从 O(n) 降到 O(1)。",
      "",
      "代价是 O(n²) 的注意力矩阵，这也是后来各类稀疏 / 线性注意力改进的出发点。"
    ].join("\n"),
    cites: ["原始来源：§3.2 缩放点积注意力", "原始来源：§4 实验设置"]
  }],
};

const CANNED_ANSWERS = [
  {
    a: [
      "基于当前来源：**结论先行**——它更适合「输入即上下文、输出为结构化知识」的场景。",
      "",
      "- 摘要与翻译类任务收益最大：原文即事实基础，幻觉空间小",
      "- 强实时流式场景需要额外做缓存与切片"
    ].join("\n"),
    cites: ["原始来源：§3.2", "引用版本 #12"]
  },
  {
    a: [
      "这个问题在来源中的直接证据有限。来源主要论证**机制本身的有效性**，对工程细节着墨不多。",
      "",
      "补充一个来源之外的通识：生产落地通常还要考虑 KV 缓存与批处理策略。"
    ].join("\n"),
    cites: ["原始来源：§6 结果"]
  },
];

Object.assign(window, { platformLabels, SOURCES, DETAILS, CHAT_SEEDS, CANNED_ANSWERS });
