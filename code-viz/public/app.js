// ── State ──
let metadata = null;
let cy = null;
let activeView = "overview";
let activeFlow = "query";

/** Pipeline schematic animation (syncs rail + cytoscape + inspector). */
let flowAnimTimer = null;
let flowPhaseIdx = 0;
let flowAnimPlaying = false;

const INSPECTOR_SUF = { pipeline: "Pipeline" };

const VIEW_LABELS = {
  overview: {
    title: "总览",
    desc: "理解仓库分层、检索路径与对外暴露的工具边界。",
  },
  modules: {
    title: "RAG 检索全景",
    desc: "面向一条查询：从 MCP 入口到预处理、Hybrid 编排、Dense/Sparse、融合、精排与响应。下方卡片按阶段列出对应源码模块。",
  },
  pipeline: {
    title: "RAG 流程",
    desc: "按调用顺序可走通的主视图：先看阶段示意动画，再在步骤轨与拓扑图中对照模块路径。与「RAG 检索全景」互补——本页重在执行顺序与本仓库解析结果。",
  },
  mcp: {
    title: "MCP / 系统调用",
    desc: "JSON-RPC 方法边界与对外暴露的工具清单（tools/list · tools/call）。",
  },
  scenarios: {
    title: "场景流程",
    desc: "从用户视角串联：在线查询的架构与载荷变形；PDF 离线摄取如何把文件变成 ChunkRecord 并进索引。",
  },
};

const PKG_COLORS = {
  core: "#3b82f6",
  libs: "#22c55e",
  ingestion: "#f59e0b",
  mcp_server: "#a78bfa",
  observability: "#94a3b8",
  dashboard: "#f472b6",
};

/** Phase indices → step indices in metadata.call_flows (aligned with extract.py orders). */
const QUERY_ANIM_PHASES = [
  {
    label: "MCP 工具入口",
    schematicHint: "tools/call",
    caption: "宿主经 Stdio JSON-RPC 调用 tools/call；入口模块 query_knowledge_hub（DEV_SPEC 阶段 E）。",
    steps: [0],
  },
  {
    label: "查询预处理",
    schematicHint: "D1 · Query Proc.",
    caption: "Query Processor：关键词提取、filters 与 metadata 规范化（DEV_SPEC D1）。",
    steps: [1],
  },
  {
    label: "Hybrid Search 编排",
    schematicHint: "D5 · Hybrid",
    caption: "并行调度 Dense / Sparse 两路召回并可降级（DEV_SPEC D5）。",
    steps: [2],
  },
  {
    label: "多路召回执行",
    schematicHint: "Dense · Sparse · 索引",
    caption: "向量检索、BM25、读向量库与稀疏索引，为多路融合准备候选（D2/D3 及相关存储）。",
    steps: [3, 4, 5, 6],
  },
  {
    label: "Fusion（RRF）",
    schematicHint: "RRF · D4",
    caption: "RRF 融合排序多路结果，输出 Top-M 候选（DEV_SPEC D4）。",
    steps: [7],
  },
  {
    label: "Reranker",
    schematicHint: "D6 · 精排",
    caption: "可选 CrossEncoder / LLM 精排；异常时回退 fusion 顺序（DEV_SPEC D6）。",
    steps: [8],
  },
  {
    label: "响应组装",
    schematicHint: "E3 / E6",
    caption: "Response Builder / citations / 多模态拼装返回 MCP Client（DEV_SPEC E3/E6）。",
    steps: [9],
  },
];

const INGESTION_ANIM_PHASES = [
  {
    label: "流水线编排",
    schematicHint: "编排 · Pipeline",
    caption: "IngestionPipeline 将 Loader→Split→Transform→Embed→Upsert 串成可观测链路（DEV_SPEC §3.1.1）。",
    steps: [0],
  },
  {
    label: "文档加载",
    schematicHint: "C3 · Loader",
    caption: "PDF Loader → 统一 Document 契约（含图片占位等）（阶段 C3）。",
    steps: [1],
  },
  {
    label: "语义切分",
    schematicHint: "C4 · Chunker",
    caption: "DocumentChunker / SplitterFactory（阶段 C4）。",
    steps: [2],
  },
  {
    label: "Transform 链",
    schematicHint: "C5–C7",
    caption: "ChunkRefiner → MetadataEnricher → ImageCaptioner 等增强步骤（C5–C7）。",
    steps: [3, 4, 5],
  },
  {
    label: "批处理编排",
    schematicHint: "C10 · Batch",
    caption: "BatchProcessor 编排 dense+sparse 编码批次（C10）。",
    steps: [6],
  },
  {
    label: "双通路嵌入",
    schematicHint: "C8 / C9",
    caption: "DenseEncoder 与 SparseEncoder（BM25 统计）并行产出（C8/C9）。",
    steps: [7, 8],
  },
  {
    label: "写入存储",
    schematicHint: "C11 · C12",
    caption: "VectorUpserter + BM25Indexer：向量库与稀疏索引落盘（C11/C12）。",
    steps: [9, 10],
  },
];

const SPEC_PIPELINE_BULLETS = {
  query: {
    headline: "DEV_SPEC · 在线查询流（§5.4.2）要点",
    bullets: [
      "<strong>入口</strong>：用户查询通过 MCP Client → MCP Server（Stdio JSON-RPC），再由内部管线处理。",
      "<strong>Query Processor</strong>：关键词、filters、metadata 解析，生成结构化检索上下文。",
      "<strong>Hybrid Search</strong>：<strong>Dense（向量）</strong>与 <strong>Sparse（BM25）</strong>并行检索，经 <strong>Fusion（RRF）</strong>合并候选。",
      "<strong>Reranker</strong>：可选精排；失败时可回退到融合顺序，避免整条链路瘫痪。",
      "<strong>输出</strong>：Response Builder 生成带引用与多模态内容的响应返回宿主。",
    ],
  },
  ingestion: {
    headline: "DEV_SPEC · 摄取流水线（§3.1.1）要点",
    bullets: [
      "<strong>目标</strong>：构建统一、可配置、可观测的离线摄取链路，结果写入向量库与稀疏索引。",
      "<strong>分层抽象</strong>：Loader → Splitter → Transform → Embedding → Upsert，_factory/registry 可替换实现。",
      "<strong>双通路</strong>：<strong>Dense 向量</strong>写入向量存储；<strong>Sparse（BM25）</strong>维护倒排统计，供在线 Hybrid 使用。",
      "<strong>工程约束</strong>：幂等 upsert、批处理与追踪打点贯穿流水线（详见 DEV_SPEC 阶段 C 表格）。",
    ],
  },
};

/** GitHub heading slugs for DEV_SPEC.md (github-slugger / GFM), aligned with QUERY_ANIM_PHASES order. */
const DEV_SPEC_QUERY_PHASE_SLUGS = [
  "e3实现-toolquery_knowledge_hub",
  "d1queryprocessor关键词提取--filters-结构",
  "d5hybridsearch-编排",
  "542-在线查询流-query-flow",
  "d4fusionrrf-实现",
  "d6rerankercore-层编排--fallback",
  "e6多模态返回组装text--image",
];

const DEV_SPEC_QUERY_MODULE_SLUG = {
  "mcp_server.tools.query_knowledge_hub": "e3实现-toolquery_knowledge_hub",
  "core.query_engine.query_processor": "d1queryprocessor关键词提取--filters-结构",
  "core.query_engine.hybrid_search": "d5hybridsearch-编排",
  "core.query_engine.dense_retriever": "d2denseretriever调用-vectorstorequery",
  "core.query_engine.sparse_retriever": "d3sparseretrieverbm25-查询",
  "libs.vector_store.chroma_store": "312-检索流水线",
  "ingestion.storage.bm25_indexer": "312-检索流水线",
  "core.query_engine.fusion": "d4fusionrrf-实现",
  "core.query_engine.reranker": "d6rerankercore-层编排--fallback",
  "core.response.response_builder": "e6多模态返回组装text--image",
};

function esc(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Base blob URL without #fragment; window.__CODE_VIZ__.devSpecMarkdownUrl overrides metadata. Supports `{branch}` in the string. */
function getDevSpecMarkdownBaseUrl() {
  let raw = "";
  if (
    typeof window !== "undefined" &&
    typeof window.__CODE_VIZ__?.devSpecMarkdownUrl === "string"
  ) {
    raw = window.__CODE_VIZ__.devSpecMarkdownUrl.trim();
  }
  if (!raw && typeof metadata?.code_viz?.dev_spec_markdown_url === "string") {
    raw = metadata.code_viz.dev_spec_markdown_url.trim();
  }
  raw = raw.replace(/#.*$/, "").trimEnd();
  if (!raw) return "";
  if (raw.includes("{branch}")) {
    const b =
      (typeof window !== "undefined" &&
      typeof window.__CODE_VIZ__?.devSpecBranch === "string"
        ? window.__CODE_VIZ__.devSpecBranch.trim()
        : "") ||
      (typeof metadata?.code_viz?.origin_default_branch === "string"
        ? metadata.code_viz.origin_default_branch.trim()
        : "") ||
      "main";
    raw = raw.split("{branch}").join(b);
  }
  return raw;
}

function devSpecExternalHref(fragmentSlug) {
  const base = getDevSpecMarkdownBaseUrl();
  if (!base) return null;
  const frag = String(fragmentSlug || "").replace(/^#/, "").trim();
  if (!frag) return base;
  return `${base}#${encodeURIComponent(frag)}`;
}

function devSpecExternalLink(label, fragmentSlug, extraClass = "") {
  const href = devSpecExternalHref(fragmentSlug);
  const cls = `dev-spec-anchor${extraClass ? ` ${extraClass}` : ""}`;
  if (!href) {
    return `<span class="dev-spec-anchor dev-spec-anchor--disabled" title="在 index.html 中设置 window.__CODE_VIZ__.devSpecMarkdownUrl，或于 code-viz 运行 npm run parse（需 origin 为 github.com）后可跳转文档锚点">${esc(label)}</span>`;
  }
  return `<a class="${esc(cls)}" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}

function setInspector(key, title, html) {
  const suf = INSPECTOR_SUF[key];
  if (!suf) return;
  const ht = document.getElementById(`inspector${suf}Title`);
  const hb = document.getElementById(`inspector${suf}Body`);
  if (!ht || !hb) return;
  ht.textContent = title;
  hb.innerHTML = html;
}

// ── Init ──
document.addEventListener("DOMContentLoaded", () => {
  if (typeof cytoscape === "undefined") {
    const b = document.getElementById("errBox");
    b.style.display = "block";
    b.innerHTML =
      "<strong>未能加载 Cytoscape</strong><br>请检查网络或使用 <code>npm start</code> 打开本站（勿用 file://）。";
    return;
  }
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      themeVariables: {
        fontFamily: '"IBM Plex Sans", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        fontSize: "14px",
        primaryColor: "#1d3f5f",
        primaryTextColor: "#f0f9ff",
        primaryBorderColor: "rgba(56,189,248,0.45)",
        secondaryColor: "#0b1624",
        tertiaryColor: "#132a3f",
        lineColor: "#5c9fd4",
        mainBkg: "#152837",
        textColor: "#e8eef7",
        border1: "#2d4a62",
        border2: "#38bdf8",
        clusterBkg: "rgba(11,21,34,0.72)",
        clusterBorder: "rgba(56,189,248,0.22)",
        edgeLabelBackground: "#111921",
        titleColor: "#7dd3fc",
        nodeTextColor: "#f1f5f9",
      },
      flowchart: {
        htmlLabels: true,
        curve: "basis",
        padding: 10,
        nodeSpacing: 52,
        rankSpacing: 56,
      },
      class: {
        htmlLabels: true,
      },
    });
  }
  window.addEventListener("resize", () => {
    if (cy) cy.resize();
  });
  setupNavigation();
  setupPipelineToggle();
  setupSSE();
  setupFlowAnimationUi();
  setupFlowSchematicDelegation();
  setupPipelineKeyboardShortcuts();
  document.getElementById("jumpToPipelineFromRetrieval")?.addEventListener("click", () => {
    document.querySelector('.nav-btn[data-view="pipeline"]')?.click();
  });
  setupScenarioPage();
  loadData();
});

async function loadData() {
  try {
    const res = await fetch("/api/metadata");
    const data = await res.json();
    if (!res.ok || !data.stats) throw new Error(data.error || `HTTP ${res.status}`);
    metadata = data;
    setStatus("ok", "数据已加载");
    refreshActiveView();
  } catch (e) {
    console.error(e);
    setStatus("warn", "API 不可用，尝试缓存…");
    try {
      const res = await fetch("metadata.json");
      metadata = await res.json();
      if (!metadata.stats) throw new Error("bad cache");
      setStatus("ok", "缓存 metadata.json");
      refreshActiveView();
    } catch (_) {
      setStatus("off", "无法加载数据");
      document.getElementById("overviewBento").innerHTML =
        `<div class="card"><h2>错误</h2><p>无法获取元数据。请在 <code>code-viz</code> 目录运行 <code>npm run parse</code> 后刷新。</p></div>`;
    }
  }
}

function setStatus(mode, text) {
  const dot = document.getElementById("statusDot");
  dot.classList.remove("warn", "off");
  if (mode === "warn") dot.classList.add("warn");
  if (mode === "off") dot.classList.add("off");
  document.getElementById("statusText").textContent = text;
}

function setupSSE() {
  const evt = new EventSource("/api/events");
  evt.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === "reload") loadData();
    } catch (_) {}
  };
  evt.onerror = () => setStatus("warn", "实时连接断开（仍可浏览）");
}

function setupNavigation() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach((b) => {
        b.classList.remove("active");
        b.removeAttribute("aria-current");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-current", "page");
      showView(btn.dataset.view);
    });
  });
}

function showView(view) {
  hideDiagramHoverTip();
  stopFlowAnimation();
  activeView = view;
  destroyCy();

  document.querySelectorAll(".view-section").forEach((el) => el.classList.remove("active"));
  const section = document.getElementById(`view-${view}`);
  if (section) section.classList.add("active");

  const meta = VIEW_LABELS[view] || VIEW_LABELS.overview;
  document.getElementById("topTitle").textContent = meta.title;
  document.getElementById("topDesc").textContent = meta.desc;

  refreshActiveView();
}

function refreshActiveView() {
  if (activeView === "scenarios") {
    renderScenariosView().catch(() => {});
    return;
  }
  if (!metadata) return;
  if (activeView === "overview") renderOverview();
  else if (activeView === "modules") renderRetrievalOverview().catch(() => {});
  else if (activeView === "pipeline") renderPipelineView();
  else if (activeView === "mcp") renderMcpView();
}

// ── Overview ──
function renderOverview() {
  const st = metadata.stats;
  const pkgs = st.packages || [];
  document.getElementById("overviewBento").innerHTML = `
    <div class="card">
      <h2>仓库规模</h2>
      <div class="stat-grid">
        <div><div class="stat-val">${st.total_modules}</div><div class="stat-label">模块</div></div>
        <div><div class="stat-val">${st.total_classes}</div><div class="stat-label">类</div></div>
        <div><div class="stat-val">${st.total_import_edges}</div><div class="stat-label">内部依赖边</div></div>
        <div><div class="stat-val">${(metadata.mcp_tools || []).length}</div><div class="stat-label">MCP 工具</div></div>
      </div>
    </div>
    <div class="card">
      <h2>这个页面做什么</h2>
      <p><strong>RAG 检索全景</strong>按「检索阶段」说明从 MCP 工具到向量/BM25 召回、RRF、精排与回复组装的链路，并挂载各阶段涉及的 <code>src/</code> 模块。</p>
      <p style="margin-top:10px"><strong>场景流程</strong>用「宿主查询」与「PDF 摄取」两条故事线说明架构、数据流与 <code>core.types</code> 的形态变化。</p>
      <p style="margin-top:10px"><strong>MCP</strong>列出宿主（IDE / Agent）可调用的工具名与入参 JSON Schema。</p>
    </div>
    <div class="card">
      <h2>包前缀（与图例一致）</h2>
      <div class="pkg-pills">
        ${pkgs
          .map((p) => {
            const c = PKG_COLORS[p] || "#64748b";
            return `<span class="pkg-pill" style="border-color:${c};color:${c}">${esc(p)}</span>`;
          })
          .join("")}
      </div>
    </div>
    <div class="card">
      <h2>快捷跳转</h2>
      <div class="jump-row">
        <button type="button" class="jump-btn" data-jump="modules">打开 RAG 检索全景</button>
        <button type="button" class="jump-btn" data-jump="pipeline">打开 RAG 流程</button>
        <button type="button" class="jump-btn" data-jump="scenarios">打开场景流程</button>
        <button type="button" class="jump-btn" data-jump="mcp">查看 MCP 工具</button>
      </div>
    </div>
    <div class="card">
      <h2>与 DEV_SPEC 对齐</h2>
      <p>RAG 流程页的<strong>要点列表与阶段动画</strong>摘录并对齐仓库根目录 <code>DEV_SPEC.md</code>（在线查询 §5.4.2、摄取 §3.1.1、MCP 阶段 E）。左侧步骤序列仍来自对 <code>src/</code> 的 AST 解析。</p>
    </div>`;

  document.querySelectorAll(".jump-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const v = btn.dataset.jump;
      document.querySelector(`.nav-btn[data-view="${v}"]`)?.click();
    });
  });
}

// ── Cytoscape ──
function destroyCy() {
  if (cy) {
    cy.destroy();
    cy = null;
  }
}

function initCy(container, elements, layout, style, onReady) {
  destroyCy();
  cy = cytoscape({
    container,
    elements,
    style,
    layout,
    wheelSensitivity: 0.35,
    minZoom: 0.08,
    maxZoom: 3,
  });
  cy.ready(() => {
    cy.resize();
    requestAnimationFrame(() => cy.resize());
    if (onReady) onReady();
  });
  return cy;
}

let mermaidRunSeq = 0;

function mmLabel(raw) {
  let s = String(raw ?? "");
  s = s.replace(/\\/g, "/");
  s = s.replace(/[\x00-\x1f\r\n]+/g, " ");
  s = s.replace(/[\[\]|]/g, " ");
  s = s.replace(/\u2192|\u2794/g, "-");
  s = s.replace(/"/g, "'");
  if (/&/.test(s)) s = s.replace(/&(gt|lt|quot|amp);/gi, " ");
  s = s.replace(/\s+/g, " ").trim();
  s = s.replace(/:/g, "·");
  if (!s.length) return "...";
  return s.slice(0, 92);
}

function slugId(prefix, s) {
  let base = `${prefix}_${String(s).replace(/[^a-zA-Z0-9]+/g, "_")}`;
  base = base.replace(/^[^a-zA-Z]+/, "") || `${prefix}_x`;
  const out = base.slice(0, 64);
  return /^[a-zA-Z_]/.test(out) ? out : `n_${out}`;
}

/** Global floating tooltip for Mermaid + Cytoscape */
let diagramHoverLayer = null;
let diagramHoverHideT = null;

function ensureDiagramHoverTip() {
  if (diagramHoverLayer) return diagramHoverLayer;
  const el = document.createElement("div");
  el.id = "diagram-hover-tip";
  el.className = "diagram-hover-tip";
  el.setAttribute("role", "tooltip");
  el.setAttribute("aria-hidden", "true");
  document.body.appendChild(el);
  diagramHoverLayer = el;
  return el;
}

function hideDiagramHoverTip() {
  cancelDiagramHoverHide();
  const el = diagramHoverLayer || document.getElementById("diagram-hover-tip");
  if (!el) return;
  el.classList.remove("is-visible");
  el.setAttribute("aria-hidden", "true");
}

function cancelDiagramHoverHide() {
  if (diagramHoverHideT) {
    clearTimeout(diagramHoverHideT);
    diagramHoverHideT = null;
  }
}

function scheduleDiagramHoverHide(ms = 90) {
  cancelDiagramHoverHide();
  diagramHoverHideT = setTimeout(() => {
    diagramHoverHideT = null;
    hideDiagramHoverTip();
  }, ms);
}

function splitTipPayloadFromString(body) {
  const s = String(body ?? "").trim();
  const nl = s.indexOf("\n");
  if (nl === -1) return { title: "", body: s };
  return { title: s.slice(0, nl).trim(), body: s.slice(nl + 1).trim() };
}

function splitTipPayload(v) {
  if (v !== null && typeof v === "object") {
    return {
      title: String(v.title || "").trim(),
      body: String(v.body ?? "").trim(),
    };
  }
  return splitTipPayloadFromString(v);
}

function showDiagramHoverTip(clientX, clientY, title, plainBody) {
  const el = ensureDiagramHoverTip();
  cancelDiagramHoverHide();
  let titleStr = title != null ? String(title).trim() : "";
  let bodyStr = plainBody != null ? String(plainBody).trim() : "";
  if (!titleStr && bodyStr) {
    const spl = splitTipPayloadFromString(bodyStr);
    if (spl.title) {
      titleStr = spl.title;
      bodyStr = spl.body;
    }
  }
  const headHtml = titleStr ? `<div class="diagram-hover-tip-title">${esc(titleStr)}</div>` : "";
  const paras = bodyStr
    ? bodyStr
        .split(/\n\n+/)
        .map((para) => `<p>${para.split(/\n/).map((ln) => esc(ln)).join("<br>")}</p>`)
        .join("")
    : "";
  el.innerHTML = `${headHtml}<div class="diagram-hover-tip-body">${paras || (titleStr ? "" : `<p>${esc("(无详情)")}</p>`)}</div>`;
  el.style.left = "-9999px";
  el.style.top = "-9999px";
  el.classList.add("is-visible");
  el.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => {
    const pad = 14;
    const r = el.getBoundingClientRect();
    let lx = clientX + pad;
    let ty = clientY + pad;
    if (lx + r.width > window.innerWidth - 10) lx = clientX - r.width - pad;
    if (ty + r.height > window.innerHeight - 10) ty = clientY - r.height - pad;
    if (lx < 8) lx = 8;
    if (ty < 8) ty = 8;
    el.style.left = `${lx}px`;
    el.style.top = `${ty}px`;
  });
}

function resolveMermaidTipForGroupId(groupId, tipMap) {
  if (!groupId || !tipMap) return null;
  const keys = Object.keys(tipMap).sort((a, b) => b.length - a.length);
  for (const k of keys) {
    if (groupId.includes(k)) return tipMap[k];
  }
  return null;
}

function findTipMermaidGroup(evTarget, svgRoot, tipMap) {
  let cur = evTarget;
  while (cur && cur !== svgRoot) {
    if (cur.tagName === "g" && typeof cur.closest === "function" && cur.closest("defs")) {
      cur = cur.parentElement;
      continue;
    }
    if (cur.tagName === "g") {
      const gid = cur.getAttribute("id");
      if (gid && resolveMermaidTipForGroupId(gid, tipMap)) return cur;
    }
    cur = cur.parentElement;
  }
  return null;
}

function setMermaidHostTipMap(hostEl, tipMap) {
  if (!hostEl) return;
  if (tipMap && typeof tipMap === "object") {
    hostEl._mermaidTipMap = tipMap;
  } else {
    hostEl._mermaidTipMap = null;
  }
}

function bindMermaidHostTooltips(hostEl) {
  if (!hostEl || hostEl.dataset.mermaidTipDelegation === "1") return;
  hostEl.dataset.mermaidTipDelegation = "1";
  hostEl.addEventListener(
    "pointermove",
    (e) => {
      const map = hostEl._mermaidTipMap;
      const svg = hostEl.querySelector("svg");
      if (!svg || !map || typeof map !== "object" || Object.keys(map).length === 0) {
        scheduleDiagramHoverHide(70);
        return;
      }
      const hit = findTipMermaidGroup(e.target, svg, map);
      if (!hit) {
        scheduleDiagramHoverHide(70);
        return;
      }
      const raw = resolveMermaidTipForGroupId(hit.id, map);
      if (!raw) {
        scheduleDiagramHoverHide(70);
        return;
      }
      const tp = splitTipPayload(raw);
      showDiagramHoverTip(e.clientX, e.clientY, tp.title, tp.body.length ? tp.body : raw.trim());
    },
    { passive: true },
  );
  hostEl.addEventListener("pointerleave", () => scheduleDiagramHoverHide(120), { passive: true });
}

function bindCyNodeHoverTips() {
  if (!cy) return;
  cy.off("mouseover.nodeTip mousemove.nodeTip mouseout.nodeTip");

  function showEvt(evt) {
    const d = evt.target.data();
    const titleStr = `${d.fullLabel || d.label || d.id}`;
    const st = metadata?.call_flows?.[activeFlow]?.find?.((x) => x.module_id === (d.fullLabel || d.id));
    const chunks = [];
    if (d.step !== undefined && d.step !== null) chunks.push(`步骤序号 · ${String(d.step)}`);
    if (d.path) chunks.push(`路径 · ${String(d.path)}`);
    if (d.package) chunks.push(`顶层包 · ${String(d.package)}`);
    if (st && String(st.docstring || "").trim()) {
      const one = String(st.docstring).trim().split("\n")[0];
      chunks.push(one);
    }
    if (Array.isArray(d.classes) && d.classes.length) {
      const sn = d.classes
        .slice(0, 2)
        .map((cls) =>
          `${cls.name} (${(cls.methods || []).slice(0, 6).join(", ")}${(cls.methods || []).length > 6 ? " …" : ""})`,
        );
      if (sn.length) chunks.push(`类型节选 · ${sn.join("；")}`);
    }
    const bodyStr = chunks.filter(Boolean).join("\n\n");
    showDiagramHoverTip(
      evt.originalEvent.clientX,
      evt.originalEvent.clientY,
      titleStr.trim() ? titleStr.trim() : "模块",
      bodyStr.trim().length ? bodyStr : "点击节点后在右侧 Inspector 查看文档与类型摘要",
    );
  }

  cy.on("mouseover.nodeTip", "node", showEvt);
  cy.on("mousemove.nodeTip", "node", showEvt);
  cy.on("mouseout.nodeTip", "node", () => scheduleDiagramHoverHide(120));
}

async function flushMermaidHost(hostEl, source, tipMap) {
  if (!hostEl) return;
  setMermaidHostTipMap(hostEl, tipMap);
  const text = source || "";
  if (!text.trim()) {
    hostEl.innerHTML = `<div class="diagram-empty">暂无内容</div>`;
    hideDiagramHoverTip();
    return;
  }
  if (typeof mermaid === "undefined") {
    hostEl.innerHTML = `<pre class="mermaid-fallback">${esc(text)}</pre>`;
    return;
  }
  mermaidRunSeq += 1;
  const uid = slugId(`d${hostEl.id || "h"}_${mermaidRunSeq}`, `${performance.now()}`).replace(/[^a-zA-Z0-9_]/g, "_");
  try {
    const { svg, bindFunctions } = await mermaid.render(uid, text, hostEl);
    hostEl.innerHTML = svg;
    if (typeof bindFunctions === "function") bindFunctions(hostEl);
    bindMermaidHostTooltips(hostEl);
  } catch (e) {
    hostEl.innerHTML = `<pre class="mermaid-fallback">${esc(text)}</pre><div class="diagram-err">${esc(e.message)}</div>`;
    hideDiagramHoverTip();
  }
}

function buildRetrievalOverviewMermaid() {
  const edge = (text) => mmLabel(text);
  function nodeLine(id, labelZh) {
    return `  ${id}["${mmLabel(labelZh)}"]`;
  }

  const mcp = slugId("qv", "mcp_tool");
  const qp = slugId("qv", "query_processor");
  const hy = slugId("qv", "hybrid_search");
  const dr = slugId("qv", "dense_retriever");
  const sr = slugId("qv", "sparse_retriever");
  const vs = slugId("qv", "chroma_store");
  const bm = slugId("qv", "bm25_index");
  const fu = slugId("qv", "fusion_rrf");
  const mf = slugId("qv", "metadata_filter");
  const rer = slugId("qv", "reranker");
  const rb = slugId("qv", "response_builder");
  const sgpar = slugId("sg_qv", "parallel_recall");

  function inner(id, labelZh) {
    return `    ${id}["${mmLabel(labelZh)}"]`;
  }

  const tips = {
    [mcp]:
      "① MCP · query_knowledge_hub\n宿主经 tools/call 进入；解析 query/top_k。\n源码：src/mcp_server/tools/query_knowledge_hub.py。\n负责组织 QueryProcessor · Hybrid · Reranker · Builder。",
    [qp]:
      "② QueryProcessor · D1\n规范化查询文本、抽出关键词候选、对齐 filters。\n产物：frozen dataclass ProcessedQuery。\n源码：src/core/query_engine/query_processor.py。",
    [hy]:
      "③ HybridSearch · D5\n并行 submit Dense/Sparse futures；fuse 后对列表做 chunk metadata 与用户 filters 对齐。\n源码：src/core/query_engine/hybrid_search.py。",
    [dr]:
      "④ DenseRetriever · D2\nembed_query 后向量库相似度召回 Top-K。\n依赖 EmbeddingFactory · VectorStoreFactory。\n源码：src/core/query_engine/dense_retriever.py。",
    [sr]:
      "⑤ SparseRetriever · D3\nBM25 postings + hydrate 条目；可走向量库补齐文本。\n源码：src/core/query_engine/sparse_retriever.py。",
    [vs]:
      "ChromaStore\n向量侧集合读写：query/get_by_ids 等。\n供 Dense 与其它读路径。\n源码：src/libs/vector_store/chroma_store.py。",
    [bm]:
      "BM25Indexer\n稀疏侧倒排与 query；离线摄取阶段写入，在线稀疏召回读取。\n源码：src/ingestion/storage/bm25_indexer.py。",
    [fu]:
      "⑥ Fusion · RRF · D4\n多路名次融合为一张 Top-M 列表。\n源码：src/core/query_engine/fusion.py。",
    [mf]:
      "⑦ Hybrid 内 metadata_filters\n位于 fuse 之后：按 chunk.metadata 与用户 filters 滤掉不合规命中。\n方法：HybridSearch._apply_metadata_filters。\n随后在 query_knowledge_hub 中再走 Reranker。",
    [rer]:
      "⑧ Reranker · D6\n在工具层对已返回的 RetrievalResult 列表精排。\n可选用 CrossEncoder/LLM，失败沿用 fusion 序。\n源码：src/core/query_engine/reranker.py。",
    [rb]:
      "⑨ ResponseBuilder · E\nCitationGenerator · MultimodalAssembler · Markdown 拼装为 MCP dict。\n源码：src/core/response/response_builder.py。",
    [sgpar]:
      "并行召回子图\nDense 与 Sparse 两路互不阻塞并行跑；各自读存储再回到 Fusion。",
  };

  const diagram = [
    `%%{init: {'theme':'dark','flowchart':{'curve':'basis','padding':18,'rankSpacing':72,'nodeSpacing':56}}}%%`,
    "flowchart TB",
    nodeLine(mcp, "① 工具入口 query_knowledge_hub · MCP tools/call 进入"),
    nodeLine(qp, "② 查询预处理 QueryProcessor · D1 · 抽关键词 · 规整 filters · 规整问句文本"),
    nodeLine(hy, "③ 混合编排 HybridSearch · D5 · 线程池并行提交 dense/sparse"),
    `  subgraph ${sgpar}["${mmLabel("并行多路召回：两路各自打分，再交给下游融合（RRF）")}"]`,
    inner(dr, "④ 稠密向量召回 DenseRetriever · D2 · 先 embed 再问向量库 Top-K"),
    inner(sr, "⑤ 稀疏词法召回 SparseRetriever · D3 · BM25 + 回填正文"),
    "  end",
    nodeLine(vs, "向量库 Chroma · 集合 query / get_by_ids · 稠密读写"),
    nodeLine(bm, "稀疏索引 BM25Indexer · 倒排落盘并可在线 query"),
    nodeLine(fu, "⑥ 多路融合 Fusion · RRF · D4 · 合成一份 Top-M 候选"),
    nodeLine(mf, "⑦ 片段元数据过滤 Hybrid 融合后 · 对齐用户 filters · _apply_metadata_filters"),
    nodeLine(rer, "⑧ 结果重排序 Reranker · D6 · 可选用 CrossEncoder/LLM · 失败则沿用融合序"),
    nodeLine(rb, "⑨ 响应组装 ResponseBuilder · 引用 / 多模态 / Markdown 输出 MCP 字典"),

    `  ${mcp} --> ${qp}`,
    `  ${qp} -->|${edge("生成 ProcessedQuery 驱动后续")}| ${hy}`,
    `  ${hy} --> ${dr}`,
    `  ${hy} --> ${sr}`,
    `  ${dr} -.->|${edge("向量近邻检索")}| ${vs}`,
    `  ${sr} -.->|${edge("BM25 + 回填（hydrate）条目")}| ${bm}`,
    `  ${dr} -->|${edge("稠密路有序候选")}| ${fu}`,
    `  ${sr} -->|${edge("稀疏路有序候选")}| ${fu}`,
    `  ${fu} -->|${edge("名次融合汇总")}| ${mf}`,
    `  ${mf} -->|${edge("Hybrid 返回后工具内再 rerank")}| ${rer}`,
    `  ${rer} -->|${edge("MCP JSON：正文与引用片段等")}| ${rb}`,
  ].join("\n");

  return { diagram, tips };
}

function retrievalPhaseStepHtml(step) {
  if (!step) return "";
  const firstLine = (step.docstring || "").trim().split("\n")[0] || "";
  const accent = PKG_COLORS[step.package] || "#64748b";
  const slug = DEV_SPEC_QUERY_MODULE_SLUG[step.module_id];
  const devRef = slug
    ? `<div class="aspect-dev-ref">${devSpecExternalLink("DEV_SPEC", slug)}</div>`
    : "";
  return `<div class="aspect-step" style="border-left-color:${accent}"><code>${esc(step.module_id)}</code><div class="aspect-path">${esc(
    step.path || "",
  )}</div>${firstLine ? `<p class="aspect-doc">${esc(firstLine)}</p>` : ""}${devRef}</div>`;
}

async function renderRetrievalOverview() {
  const gridHost = document.getElementById("retrievalAspectsHost");
  const mHost = document.getElementById("retrievalOverviewMermaid");
  const steps = metadata?.call_flows?.query;

  if (!gridHost || !mHost) return;

  const pack = buildRetrievalOverviewMermaid();

  await flushMermaidHost(mHost, steps?.length ? pack.diagram : "", steps?.length ? pack.tips : null);

  if (!steps?.length) {
    gridHost.innerHTML =
      '<div class="diagram-empty" style="margin-top:18px">未找到查询管线步骤 · 请在 <code>code-viz</code> 运行 <code>npm run parse</code> 后刷新。</div>';
    return;
  }

  const cardsHtml = QUERY_ANIM_PHASES.map((phase, phaseIndex) => {
    const mods = phase.steps.flatMap((si) => (steps[si] ? [steps[si]] : []));
    const accent = PKG_COLORS[mods[0]?.package] || "#64748b";
    const phaseSlug = DEV_SPEC_QUERY_PHASE_SLUGS[phaseIndex];
    const phaseLink = phaseSlug
      ? `<span class="aspect-phase-ref">${devSpecExternalLink("DEV_SPEC", phaseSlug)}</span>`
      : "";
    return `<article class="aspect-card" style="border-left: 4px solid ${accent}">
      <h4 class="aspect-title"><span>${esc(phase.label)}</span>${phaseLink}</h4>
      <p class="aspect-caption">${esc(phase.caption)}</p>
      ${mods.map(retrievalPhaseStepHtml).join("")}
    </article>`;
  }).join("");

  gridHost.innerHTML = `
    <div class="aspects-intro">
      <h3 class="aspect-section-title">各阶段涉及的源码模块</h3>
      <p class="aspect-section-lead">与上方总览图一一对应；阶段标题与模块下的 <strong>DEV_SPEC</strong> 在新标签页打开文档对应章节锚点（可在本页脚本中配置 <code>window.__CODE_VIZ__.devSpecMarkdownUrl</code>，支持 <code>{branch}</code>）。未解析到托管地址时为灰色占位。需要步骤动画与拓扑联动时可切到「RAG 流程」视图。</p>
    </div>
    <div class="retrieval-aspects-grid">${cardsHtml}</div>
  `;
}

// ── 场景流程（用户查询 / PDF 摄取）──
function scenarioFlowInit() {
  return `%%{init:{'theme':'dark','flowchart':{'curve':'basis','padding':14,'rankSpacing':56,'nodeSpacing':44}}}%%`;
}

function scenarioNode(id, label) {
  return `  ${id}["${mmLabel(label)}"]`;
}

function buildScenarioQueryArchMermaid() {
  const u = slugId("sq", "user_host");
  const c = slugId("sq", "mcp_client");
  const s = slugId("sq", "mcp_server");
  const t = slugId("sq", "tool_hub");
  const e = slugId("sq", "query_core");
  const st = slugId("sq", "indexes");
  const tips = {
    [u]: "宿主\n人或 Agent IDE；发起自然语言检索请求，经 MCP Client 发往本 Server。",
    [c]:
      "MCP Client\n实现 JSON-RPC 报文收发（通常 stdio）。\n与 Server 对齐 initialize/tools/list/tools/call 序列。",
    [s]:
      "MCP Server\n解析协议会话，将 tools/call 路由至 query_knowledge_hub 等处理器。",
    [t]:
      "query_knowledge_hub\nPython 入口：拼装 QueryProcessor Hybrid Reranker ResponseBuilder。\n源码：src/mcp_server/tools/query_knowledge_hub.py。",
    [e]:
      "核心检索链路\n参见「RAG 检索」总览；此处抽象为「编排 + 读索引 + 组装回复」。",
    [st]: "已落盘索引\nChroma 向量集合 + BM25 倒排；在线读侧。",
  };
  const diagram = [
    scenarioFlowInit(),
    "flowchart TB",
    scenarioNode(u, "宿主侧 · 人或 Agent IDE · 发起自然语言检索"),
    scenarioNode(c, "MCP 客户端 Client · JSON-RPC（通常 stdio）"),
    scenarioNode(s, "MCP 服务端 Server · 会话初始化与工具分发"),
    scenarioNode(t, "工具处理器 query_knowledge_hub · Python 拼装整条检索链"),
    scenarioNode(e, "核心检索 · 预处理 / Hybrid 编排 / RR 融合筛选 / Reranker / 应答组装"),
    scenarioNode(st, "已建成的索引 · Chroma 向量集合 · BM25 倒排可读"),
    `  ${u} --> ${c}`,
    `  ${c} -->|${mmLabel("发出 JSON-RPC 请求")}| ${s}`,
    `  ${s} -->|${mmLabel("tools/call 路由到处理器")}| ${t}`,
    `  ${t} --> ${e}`,
    `  ${e} -.->|${mmLabel("读写在线向量与稀疏索引")}| ${st}`,
    `  ${e} -->|${mmLabel("组装 dict 工具返回结构")}| ${t}`,
    `  ${t} -->|${mmLabel("封装 result 答复宿主")}| ${s}`,
    `  ${s} -->|${mmLabel("下行 JSON-RPC 响应")}| ${c}`,
    `  ${c} --> ${u}`,
  ].join("\n");
  return { diagram, tips };
}

function buildScenarioQueryDataflowMermaid() {
  const a = slugId("dfq", "mcp_args");
  const pq = slugId("dfq", "processed_q");
  const hy = slugId("dfq", "hybrid_search");
  const hit = slugId("dfq", "hits");
  const rr = slugId("dfq", "rerank");
  const out = slugId("dfq", "response");
  const tips = {
    [a]: "MCP arguments\nJSON 级参数：query 必填；top_k 限制条数；filters 与 ProcessedQuery.filters 对齐。",
    [pq]:
      "ProcessedQuery\nQueryProcessor.process 输出：raw/normalized/keywords/filters。\n驱动 Hybrid 与稀疏统计。",
    [hy]: "HybridSearch.search\n内部完成双路召回、RRF、metadata_filters；返回 List[RetrievalResult]。",
    [hit]: "RetrievalResult 列表\ncore.types.RetrievalResult：chunk_id score text metadata。",
    [rr]: "Reranker.rerank\n在工具层二次排序；可降级。",
    [out]: "ResponseBuilder.build\n生成 MCP tools/call 的 content 结构与引用。",
  };
  const diagram = [
    scenarioFlowInit(),
    "flowchart TB",
    scenarioNode(a, "MCP 入参 JSON · query 必填 · top_k 可选 · filters 可选"),
    scenarioNode(pq, "预处理结果 ProcessedQuery · 规整问句 · 词条 · filters"),
    scenarioNode(hy, "HybridSearch.search · 并行召回 · RRF 融合 · metadata 对齐"),
    scenarioNode(hit, "命中列表 RetrievalResult[] · chunk / 分数 / 文本快照片段 / 元数据"),
    scenarioNode(rr, "二次排序 · Reranker.rerank · 可选用模型 · 异常则保持原序"),
    scenarioNode(out, "出站响应 · ResponseBuilder.build · MCP 工具返回值 dict"),
    `  ${a} -->|${mmLabel("QueryProcessor.process")}| ${pq}`,
    `  ${pq} -->|${mmLabel("HybridSearch.search")}| ${hy}`,
    `  ${hy} --> ${hit}`,
    `  ${hit} -->|${mmLabel("工具层再做精排")}| ${rr}`,
    `  ${rr} --> ${out}`,
  ].join("\n");
  return { diagram, tips };
}

function buildScenarioQueryTypesMermaid() {
  const tips = {
    ProcessedQueryView:
      "ProcessedQueryView（示意）\n对应 core.query_engine.QueryProcessor 产出的 Frozen dataclass：raw/normalized/keywords/filters。\n对齐 DEV_SPEC · D1。",
    RetrievalResultView:
      "RetrievalResultView（示意）\n对应 core.types.RetrievalResult：chunk_id、score、检索文本快照、可选 metadata。\n用于精排与 ResponseBuilder。",
  };
  const diagram = [
    `%%{init:{'theme':'dark'}}%%`,
    "classDiagram",
    "direction TB",
    "class ProcessedQueryView {",
    "  <<预处理查询快照 · Frozen ProcessedQuery · D1>>",
    "  raw_query",
    "  normalized_query",
    "  keywords",
    "  filters",
    "}",
    "class RetrievalResultView {",
    "  <<单次命中 · RetrievalResult · 供精排/组装>>",
    "  chunk_id",
    "  score",
    "  text",
    "  metadata",
    "}",
    "ProcessedQueryView --> RetrievalResultView : Hybrid 召回产生多条命中",
    'note right of ProcessedQueryView : 预处理输出驱动 Hybrid 双路与 filters',
    'note right of RetrievalResultView : 再走 Reranker 与 ResponseBuilder 拼装 MCP 返回值',
  ].join("\n");
  return { diagram, tips };
}

function buildScenarioIngestArchMermaid() {
  const pdf = slugId("iga", "pdf_file");
  const load = slugId("iga", "pdf_loader");
  const pipe = slugId("iga", "ingest_pipe");
  const enc = slugId("iga", "encoders");
  const ups = slugId("iga", "upsert");
  const v = slugId("iga", "chroma");
  const b = slugId("iga", "bm25");
  const tips = {
    [pdf]: "PDF 文件\n本地或挂载路径；作为 Loader 输入。",
    [load]: "PdfLoader\n逐页抽文本，可选图片落盘并在正文插入 [IMAGE:id] 占位。\n源码：src/libs/loader/pdf_loader.py。",
    [pipe]: "IngestionPipeline\nChunker + Transform 链 + BatchProcessor 编排。\n源码：src/ingestion/pipeline.py。",
    [enc]: "DenseEncoder / SparseEncoder\n把文本批编码为向量与稀疏统计。",
    [ups]: "VectorUpserter + BM25Indexer\n写向量库与维护倒排。",
    [v]: "Chroma 集合\n持久化向量与元数据。",
    [b]: "BM25 索引文件\n供在线 SparseRetriever 加载。",
  };
  const diagram = [
    scenarioFlowInit(),
    "flowchart TB",
    scenarioNode(pdf, "离线 PDF · 本地或挂载路径输入"),
    scenarioNode(load, "载入器 PdfLoader · 分页抽文本 · 可选图片占位符"),
    scenarioNode(pipe, "摄取流水线 IngestionPipeline · 切 Chunk · Transform 链路 · Batch 编排"),
    scenarioNode(enc, "双通路编码 DenseEncoder · SparseEncoder · 向量 + 稀疏统计"),
    scenarioNode(ups, "入库 VectorUpserter · BM25Indexer · 写向量与倒排"),
    scenarioNode(v, "向量侧持久化 Chroma 集合"),
    scenarioNode(b, "稀疏侧 BM25 索引文件 · 在线检索可读"),
    `  ${pdf} --> ${load}`,
    `  ${load} -->|${mmLabel("产出领域对象 Document · core.types")}| ${pipe}`,
    `  ${pipe} --> ${enc}`,
    `  ${enc} --> ${ups}`,
    `  ${ups} --> ${v}`,
    `  ${ups} --> ${b}`,
  ].join("\n");
  return { diagram, tips };
}

function buildScenarioIngestDataflowMermaid() {
  const raw = slugId("igf", "pdf_pages");
  const doc = slugId("igf", "document");
  const chk = slugId("igf", "chunks");
  const tx = slugId("igf", "transform");
  const rec = slugId("igf", "chunk_record");
  const st = slugId("igf", "persist");
  const tips = {
    [raw]:
      "PDF reader\n分页读取；page 文本 concat；可按页截取图片条目。\nmetadata.page_count 在 Document 中立即可见。",
    [doc]:
      "Document · core.types\n全文 text + metadata.source_path 必填。\n正文可含 IMAGE 占位符；metadata.images[*] 记录 offset/length。\n对齐 types.py DOCUMENT 契约。",
    [chk]: "Chunk 列表\n语义切分后带 start_offset/end_offset，可回溯 source_ref。",
    [tx]:
      "Transform 步骤\nChunkRefiner / MetadataEnricher / ImageCaptioner 等。\n不改变「Chunk」实体类型语义，增补 metadata/text。",
    [rec]:
      "ChunkRecord\n挂上 dense_vector 与稀疏侧统计。\n对齐 types.py ChunkRecord。",
    [st]: "持久化\nupsert 向量；BM25 合并词项与 df。",
  };
  const diagram = [
    scenarioFlowInit(),
    "flowchart TB",
    scenarioNode(raw, "PDF 读取 · 逐页正文 · 可选导出图片资源"),
    scenarioNode(doc, "文档实体 Document · 全文 + 必含 source_path · 页数 · 图片占位或 images 元数据"),
    scenarioNode(chk, "语义切片 Chunk 列表 · 起止偏移 · 溯源 source_ref"),
    scenarioNode(tx, "变换链 · Refiner 清洗 · Enricher 补元数据 · Captioner 图片说明"),
    scenarioNode(rec, "可索引记录 ChunkRecord · 稠密向量 · 稀疏向量"),
    scenarioNode(st, "持久化 · upsert 向量库 · 合并 BM25 词项与 df"),
    `  ${raw} -->|${mmLabel("PdfLoader.load")}| ${doc}`,
    `  ${doc} -->|${mmLabel("DocumentChunker 切分")}| ${chk}`,
    `  ${chk} --> ${tx}`,
    `  ${tx} -->|${mmLabel("BatchProcessor 批编码")}| ${rec}`,
    `  ${rec} --> ${st}`,
  ].join("\n");
  return { diagram, tips };
}

function buildScenarioIngestTypesMermaid() {
  const tips = {
    DocumentView:
      "DocumentView（示意）\n对应 core.types.Document：id + 全文 + metadata（source_path 必填，images 可选）。\nPDF 入口后第一次「合同化」领域对象。",
    ChunkView:
      "ChunkView（示意）\n对应 core.types.Chunk：保留 offsets 与 source_ref，metadata 可继续丰富。",
    ChunkRecordView:
      "ChunkRecordView（示意）\n对应 core.types.ChunkRecord：为索引附加 dense_vector / sparse_vector。",
  };
  const diagram = [
    `%%{init:{'theme':'dark'}}%%`,
    "classDiagram",
    "direction LR",
    "class DocumentView {",
    "  <<整篇 PDF 合同化 · core.types.Document>>",
    "  id",
    "  text",
    "  metadata",
    "}",
    "class ChunkView {",
    "  <<语义切片 · core.types.Chunk>>",
    "  id",
    "  text",
    "  metadata",
    "  start_offset",
    "  end_offset",
    "  source_ref",
    "}",
    "class ChunkRecordView {",
    "  <<待写入索引 · core.types.ChunkRecord>>",
    "  id",
    "  text",
    "  metadata",
    "  dense_vector",
    "  sparse_vector",
    "}",
    "DocumentView --> ChunkView : 切分 · 保留溯源",
    "ChunkView --> ChunkRecordView : 编码 · 挂向量与稀疏特征",
    'note right of DocumentView : Loader 后首份领域对象 含全文与源路径等元数据',
    'note right of ChunkRecordView : Upserter 与 BM25Indexer 落盘 供在线 Hybrid 检索读取',
  ].join("\n");
  return { diagram, tips };
}

function setupScenarioPage() {
  const root = document.getElementById("scenario-page");
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";
  root.querySelectorAll(".scenario-subtab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.scenario;
      root.querySelectorAll(".scenario-subtab").forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      root.querySelectorAll(".scenario-panel").forEach((p) => {
        p.classList.toggle("active", p.id === `scenario-panel-${key}`);
      });
      renderScenarioCharts(key).catch(() => {});
    });
  });
}

async function renderScenarioCharts(which) {
  if (typeof mermaid === "undefined") return;
  if (which === "ingest") {
    const ia = buildScenarioIngestArchMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-ingest-arch"), ia.diagram, ia.tips);
    const iflow = buildScenarioIngestDataflowMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-ingest-flow"), iflow.diagram, iflow.tips);
    const it = buildScenarioIngestTypesMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-ingest-types"), it.diagram, it.tips);
  } else {
    const qa = buildScenarioQueryArchMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-query-arch"), qa.diagram, qa.tips);
    const qf = buildScenarioQueryDataflowMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-query-flow"), qf.diagram, qf.tips);
    const qt = buildScenarioQueryTypesMermaid();
    await flushMermaidHost(document.getElementById("scenario-mermaid-query-types"), qt.diagram, qt.tips);
  }
}

async function renderScenariosView() {
  setupScenarioPage();
  if (!document.getElementById("scenario-page")) return;
  const tab = document.querySelector("#scenario-page .scenario-subtab.active");
  const key = tab?.dataset.scenario || "query";
  await renderScenarioCharts(key);
}

function phaseStepRangeLabel(flowSteps, stepIndices) {
  const nums = stepIndices.map((si) => {
    const st = flowSteps[si];
    if (!st) return si + 1;
    return st.step !== undefined && st.step !== null ? Number(st.step) : si + 1;
  });
  if (!nums.length) return "";
  const lo = Math.min(...nums);
  const hi = Math.max(...nums);
  return lo === hi ? `步骤 ${lo}` : `步骤 ${lo}–${hi}`;
}

/** Split long phase titles onto two lines (segments separated by ·) for vertical stacks. */
function splitPhaseTitleForStack(title) {
  const t = String(title ?? "").trim();
  if (!t) return [""];
  const segs = t.split(/\s·\s/);
  if (segs.length <= 2) return segs.length === 2 ? [segs[0], segs[1]] : [t];
  const mid = Math.ceil(segs.length / 2);
  return [segs.slice(0, mid).join(" · "), segs.slice(mid).join(" · ")];
}

/** Vertical phase card: centered column, stacks with `#pipelineFlowKbRegion` / step rail. */
function phaseBoxSvgVertical(cx, boxTop, boxW, boxH, title, sub, rangeLine, phaseIdx, caption) {
  const left = cx - boxW / 2;
  const midX = cx;
  const cap = (caption || "").trim();
  const aria = cap ? `${title}。${cap}` : title;
  const [t1, t2] = splitPhaseTitleForStack(title);
  const two = t2 && String(t2).trim().length > 0;

  let yLabel1 = boxTop + 20;
  let yLabel2 = boxTop + 34;
  let ySub = two ? boxTop + 50 : boxTop + 44;
  let yRange = two ? boxTop + 66 : boxTop + 62;

  const lines = `<text class="ph-label" x="${midX}" y="${yLabel1}" text-anchor="middle">${esc(t1)}</text>${
    two ? `<text class="ph-label ph-label-second" x="${midX}" y="${yLabel2}" text-anchor="middle">${esc(t2.trim())}</text>` : ""
  }<text class="ph-sub" x="${midX}" y="${ySub}" text-anchor="middle">${esc(sub)}</text><text class="ph-range" x="${midX}" y="${yRange}" text-anchor="middle">${esc(rangeLine)}</text>`;

  return `<g class="ph-box" role="button" tabindex="0" data-jump-phase="${phaseIdx}" aria-label="${esc(aria)}"><rect x="${left}" y="${boxTop}" width="${boxW}" height="${boxH}" rx="10" />${lines}</g>`;
}

/** Vertical stage stack (TB): aligns with downward reading — same direction as step rail / graph TB. */
function verticalPhaseFlowSvg(labels, subs, ranges, captions) {
  const n = labels.length;
  const boxW = 236;
  const boxH = 84;
  const gap = 10;
  const padT = 6;
  const padB = 14;
  const svgW = boxW + 28;
  const cx = svgW / 2;

  const tops = [];
  let y = padT;
  for (let i = 0; i < n; i++) {
    tops.push(y);
    y += boxH + gap;
  }
  const svgH = tops[n - 1] + boxH + padB;

  let conn = "";
  for (let i = 0; i < n - 1; i++) {
    const y0 = tops[i] + boxH;
    const y1 = tops[i + 1];
    conn += `<path class="flow-connector" d="M ${cx} ${y0} L ${cx} ${y1}" />`;
  }

  const caps = captions || [];
  const boxes = labels.map((_, i) =>
    phaseBoxSvgVertical(cx, tops[i], boxW, boxH, labels[i], subs[i], ranges[i], i, caps[i]),
  ).join("");

  return `<svg class="flow-svg flow-svg--vertical" viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMin meet" aria-label="逻辑阶段竖向示意图，自上而下可点击跳转"><defs><marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6 Z" fill="#475569"/></marker></defs>${conn}${boxes}</svg>`;
}

function renderFlowSchematic() {
  const host = document.getElementById("flowSchematicHost");
  if (!host) return;
  const flowSteps = metadata?.call_flows?.[activeFlow];
  if (!flowSteps || !flowSteps.length) {
    host.innerHTML = "";
    return;
  }
  const phases = activeFlow === "query" ? QUERY_ANIM_PHASES : INGESTION_ANIM_PHASES;
  const labels = phases.map((p) => p.label);
  const subs = phases.map((p) => p.schematicHint || "");
  const ranges = phases.map((p) => phaseStepRangeLabel(flowSteps, p.steps));
  const caps = phases.map((p) => p.caption);
  host.innerHTML = verticalPhaseFlowSvg(labels, subs, ranges, caps);
}

function renderPipelineSpecReading() {
  const block = SPEC_PIPELINE_BULLETS[activeFlow];
  const el = document.getElementById("pipelineSpecReading");
  if (!el || !block) return;
  el.innerHTML = `<div class="spec-h">${esc(block.headline)}</div><ul>${block.bullets.map((b) => `<li>${b}</li>`).join("")}</ul>`;
}

function getAnimPhases() {
  return activeFlow === "query" ? QUERY_ANIM_PHASES : INGESTION_ANIM_PHASES;
}

function phaseLabelForRailStep(stepIndex) {
  const hit = getAnimPhases().find((p) => p.steps.includes(stepIndex));
  return hit ? hit.label : "";
}

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function updateFlowAnimButtons() {
  const play = document.getElementById("btnFlowPlay");
  const pause = document.getElementById("btnFlowPause");
  if (!play || !pause) return;
  play.disabled = flowAnimPlaying || prefersReducedMotion();
  pause.disabled = !flowAnimPlaying;
  play.title = prefersReducedMotion() ? "系统已开启「减少动态效果」，动画已关闭" : "";
}

function pauseFlowAnimation() {
  flowAnimPlaying = false;
  if (flowAnimTimer) clearInterval(flowAnimTimer);
  flowAnimTimer = null;
  updateFlowAnimButtons();
}

function stopFlowAnimation() {
  pauseFlowAnimation();
  flowPhaseIdx = 0;
}

function startFlowAnimation() {
  if (prefersReducedMotion() || activeView !== "pipeline") return;
  pauseFlowAnimation();
  flowAnimPlaying = true;
  updateFlowAnimButtons();
  const n = getAnimPhases().length;
  applyFlowAnimationPhase(flowPhaseIdx % n);
  flowAnimTimer = setInterval(() => {
    flowPhaseIdx = (flowPhaseIdx + 1) % n;
    applyFlowAnimationPhase(flowPhaseIdx);
  }, 1500);
}

function phaseDetailHtml(phase) {
  const steps = metadata.call_flows[activeFlow];
  let list = "";
  phase.steps.forEach((si) => {
    const st = steps[si];
    if (!st) return;
    const one = (st.docstring || "").trim().split("\n")[0] || "";
    const n = st.step !== undefined && st.step !== null ? String(st.step) : String(si + 1);
    list += `<li><code>${esc(st.module_id)}</code><span class="rail-step-n">步骤 ${esc(n)}</span> · <span class="muted-inline">${esc(one)}</span></li>`;
  });
  return `<details class="insp-block insp-block--phase" open>
  <summary>阶段概要（DEV_SPEC）</summary>
  <p class="phase-lead">${esc(phase.caption)}</p>
</details>
<details class="insp-block" open>
  <summary>本阶段涉及的模块（解析顺序）</summary>
  <ul class="phase-mod-list">${list}</ul>
</details>`;
}

function syncRailHighlightFromSteps(stepIndices) {
  const set = new Set(stepIndices);
  document.querySelectorAll("#stepRail .step-item").forEach((el, i) => {
    el.classList.toggle("active", set.has(i));
  });
}

function syncGraphHighlightFromSteps(stepIndices) {
  if (!cy || !metadata?.call_flows?.[activeFlow]) return;
  const steps = metadata.call_flows[activeFlow];
  cy.elements().removeClass("highlighted");
  let union = cy.collection();
  stepIndices.forEach((si) => {
    const st = steps[si];
    if (!st) return;
    const t = cy.$id(st.module_id);
    if (t.nonempty()) union = union.union(t);
  });
  union.addClass("highlighted");
  if (union.nonempty()) cy.animate({ fit: { eles: union, padding: 68 }, duration: 280 });
}

function applyFlowAnimationPhase(idx) {
  flowPhaseIdx = idx;
  const phases = getAnimPhases();
  const p = phases[idx];
  if (!p || !metadata?.call_flows?.[activeFlow]) return;

  document.querySelectorAll("#flowSchematicHost .ph-box").forEach((box) => {
    const j = parseInt(box.dataset.jumpPhase, 10);
    box.classList.toggle("is-active", j === idx);
  });

  document.querySelectorAll("#flowSchematicHost .flow-connector").forEach((path, i) => {
    path.classList.toggle("is-lit", idx > i);
  });

  const cap = document.getElementById("flowPhaseCaption");
  if (cap) cap.innerHTML = `<span class="phase-name">${esc(p.label)}</span> ${esc(p.caption)}`;

  setInspector("pipeline", p.label, phaseDetailHtml(p));
  syncRailHighlightFromSteps(p.steps);
  syncGraphHighlightFromSteps(p.steps);

  requestAnimationFrame(() => {
    document.querySelector("#stepRail .step-item.active")?.scrollIntoView({
      block: "nearest",
      behavior: prefersReducedMotion() ? "auto" : "smooth",
    });
  });
}

function setupFlowAnimationUi() {
  const root = document.getElementById("flowAnimControls");
  if (!root || root.dataset.bound === "1") return;
  root.dataset.bound = "1";
  root.addEventListener("click", (e) => {
    const t = e.target;
    if (t.id === "btnFlowPlay") startFlowAnimation();
    if (t.id === "btnFlowPause") pauseFlowAnimation();
  });
  updateFlowAnimButtons();
}

function setupFlowSchematicDelegation() {
  const host = document.getElementById("flowSchematicHost");
  if (!host || host.dataset.delegateBound === "1") return;
  host.dataset.delegateBound = "1";
  function jumpFromPhBox(g) {
    if (!g || activeView !== "pipeline") return;
    const jp = g.dataset.jumpPhase;
    if (jp === undefined || jp === "") return;
    pauseFlowAnimation();
    flowPhaseIdx = parseInt(jp, 10);
    applyFlowAnimationPhase(flowPhaseIdx);
    updateFlowAnimButtons();
  }
  host.addEventListener("click", (e) => {
    jumpFromPhBox(e.target.closest(".ph-box"));
  });
  host.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const g = e.target.closest(".ph-box");
    if (!g) return;
    e.preventDefault();
    jumpFromPhBox(g);
  });
}

// ── Pipeline ──
function setupPipelineToggle() {
  document.querySelectorAll("#toolbarPipeline button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#toolbarPipeline button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeFlow = btn.dataset.flow;
      renderPipelineView();
    });
  });
}

function setupPipelineKeyboardShortcuts() {
  const flowPanel = document.querySelector("#view-pipeline .flow-demo-panel");
  if (!flowPanel || flowPanel.dataset.kbBound === "1") return;
  flowPanel.dataset.kbBound = "1";
  flowPanel.addEventListener("keydown", (e) => {
    if (activeView !== "pipeline" || e.code !== "Space" || e.repeat) return;
    const tag = e.target.tagName || "";
    if (tag === "BUTTON" || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (e.target.closest && e.target.closest(".flow-svg")) return;
    e.preventDefault();
    if (prefersReducedMotion()) return;
    if (flowAnimPlaying) pauseFlowAnimation();
    else startFlowAnimation();
  });

  document.addEventListener("keydown", (e) => {
    if (activeView !== "pipeline") return;
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const t = e.target;
    if (!t || !t.classList || !t.classList.contains("step-item")) return;
    e.preventDefault();
    const rail = document.getElementById("stepRail");
    const items = rail ? [...rail.querySelectorAll(".step-item")] : [];
    if (!items.length) return;
    let i = items.indexOf(t);
    if (i < 0) return;
    if (e.key === "ArrowDown") i = Math.min(i + 1, items.length - 1);
    else i = Math.max(i - 1, 0);
    const next = items[i];
    next.focus();
    next.click();
  });
}


function renderPipelineView() {
  if (!metadata || !metadata.call_flows) return;
  const steps = metadata.call_flows[activeFlow];
  if (!steps || !steps.length) return;

  renderPipelineSpecReading();
  renderFlowSchematic();
  pauseFlowAnimation();
  flowPhaseIdx = 0;

  const rail = document.getElementById("stepRail");
  rail.innerHTML = `<h3>${activeFlow === "query" ? "查询管线" : "摄取管线"}</h3>`;
  steps.forEach((step, idx) => {
    const el = document.createElement("div");
    el.className = "step-item";
    el.dataset.moduleId = step.module_id;
    el.tabIndex = 0;
    const phaseLab = phaseLabelForRailStep(idx);
    const doc = (step.docstring || "").trim().split("\n")[0] || "";
    const chip = phaseLab ? `<div class="step-phase-chip" title="与本页阶段示意一致的名称">${esc(phaseLab)}</div>` : "";
    el.innerHTML = `${chip}<div class="step-num">步骤 ${step.step || idx + 1}</div><div class="step-mod">${esc(step.module_id)}</div><div class="step-snippet">${esc(doc)}</div>`;
    el.addEventListener("click", () => {
      pauseFlowAnimation();
      rail.querySelectorAll(".step-item").forEach((x) => x.classList.remove("active"));
      el.classList.add("active");
      pipelineStepInspector(step, idx);
      document.querySelectorAll("#flowSchematicHost .ph-box").forEach((box) => box.classList.remove("is-active"));
      document.querySelectorAll("#flowSchematicHost .flow-connector").forEach((p) => p.classList.remove("is-lit"));
      const cap = document.getElementById("flowPhaseCaption");
      if (cap) cap.textContent = "手动浏览：点击下方「播放」可重新观看阶段动画。";
      if (cy) {
        const t = cy.$id(step.module_id);
        cy.elements().removeClass("highlighted");
        if (t.nonempty()) {
          t.addClass("highlighted");
          cy.animate({ fit: { eles: t, padding: 72 }, duration: 220 });
        }
      }
      updateFlowAnimButtons();
    });
    rail.appendChild(el);
  });

  renderPipelineGraph(steps);
  applyFlowAnimationPhase(0);
  updateFlowAnimButtons();
}

function pipelineStepInspector(step, railIndex) {
  const ix = typeof railIndex === "number" ? railIndex : metadata.call_flows[activeFlow].findIndex((s) => s.module_id === step.module_id);
  const phaseLab = ix >= 0 ? phaseLabelForRailStep(ix) : "";
  const phaseLine = phaseLab
    ? `<p class="step-insp-phase">阶段 · <strong>${esc(phaseLab)}</strong>（与上方示意一致）</p>`
    : "";

  let classesHtml = "";
  if (step.classes && step.classes.length) {
    step.classes.forEach((cls) => {
      classesHtml += `<div class="class-block"><strong>${esc(cls.name)}</strong>`;
      classesHtml += `<div class="tag-row">${(cls.methods || []).slice(0, 12).map((m) => `<span class="pill" style="background:var(--bg-deep);border:1px solid var(--border)">${esc(m)}()</span>`).join("")}</div>`;
      if (cls.calls && cls.calls.length) {
        classesHtml += `<p style="margin-top:8px;font-size:12px"><strong>分析到的调用名（节选）</strong></p><div class="tag-row">${cls.calls
          .slice(0, 16)
          .map((c) => `<span class="pill" style="opacity:.85">${esc(c)}</span>`)
          .join("")}</div>`;
      }
      classesHtml += `</div>`;
    });
  }

  const docBlock = step.docstring
    ? `<details class="insp-block" open>
  <summary>模块说明（docstring）</summary>
  <p class="pre-doc">${esc(step.docstring.trim())}</p>
</details>`
    : "";

  const typesBlock =
    classesHtml.length > 0
      ? `<details class="insp-block" open>
  <summary>类型与方法（AST 摘要）</summary>
  ${classesHtml}
</details>`
      : "";

  const html = `${phaseLine}
<details class="insp-block" open>
  <summary>模块与路径</summary>
  <p><code class="insp-code">${esc(step.module_id)}</code></p>
  <p class="insp-path"><code>${esc(step.path)}</code></p>
</details>
${docBlock}
${typesBlock}`;

  setInspector("pipeline", step.module_id.split(".").pop(), html);
}

function renderPipelineGraph(steps) {
  const container = document.getElementById("cy-pipeline");
  const elements = [];

  steps.forEach((step, i) => {
    const modId = step.module_id;
    const shortName = modId.split(".").pop();
    elements.push({
      data: {
        id: modId,
        label: shortName,
        fullLabel: modId,
        path: step.path,
        package: step.package,
        step: step.step || i + 1,
        classes: step.classes || [],
      },
    });

    if (i > 0) {
      const prev = steps[i - 1];
      const isParallel =
        (prev.module_id.includes("hybrid_search") && modId.includes("dense")) ||
        (prev.module_id.includes("hybrid_search") && modId.includes("sparse")) ||
        (prev.module_id.includes("dense_encoder") && modId.includes("vector_upserter")) ||
        (prev.module_id.includes("sparse_encoder") && modId.includes("bm25"));

      elements.push({
        data: {
          id: `${prev.module_id}→${modId}`,
          source: prev.module_id,
          target: modId,
          parallel: isParallel,
        },
      });
    }
  });

  if (activeFlow === "query") {
    addPipeEdge(elements, "core.query_engine.dense_retriever", "core.query_engine.fusion");
    addPipeEdge(elements, "core.query_engine.sparse_retriever", "core.query_engine.fusion");
    addPipeEdge(elements, "libs.vector_store.chroma_store", "core.query_engine.fusion");
    addPipeEdge(elements, "ingestion.storage.bm25_indexer", "core.query_engine.fusion");
    addPipeEdge(elements, "core.query_engine.reranker", "core.response.response_builder");
  } else {
    addPipeEdge(elements, "ingestion.embedding.dense_encoder", "ingestion.storage.vector_upserter");
    addPipeEdge(elements, "ingestion.embedding.sparse_encoder", "ingestion.storage.bm25_indexer");
    addPipeEdge(elements, "ingestion.storage.vector_upserter", "ingestion.storage.bm25_indexer");
    addPipeEdge(elements, "ingestion.transform.chunk_refiner", "ingestion.transform.metadata_enricher");
    addPipeEdge(elements, "ingestion.transform.metadata_enricher", "ingestion.transform.image_captioner");
    addPipeEdge(elements, "ingestion.transform.image_captioner", "ingestion.embedding.batch_processor");
    addPipeEdge(elements, "ingestion.embedding.batch_processor", "ingestion.embedding.dense_encoder");
    addPipeEdge(elements, "ingestion.embedding.batch_processor", "ingestion.embedding.sparse_encoder");
  }

  const style = [
    {
      selector: "node",
      style: {
        "background-color": (ele) => PKG_COLORS[ele.data("package")] || "#64748b",
        label: "data(label)",
        "font-size": "11px",
        "font-family": "JetBrains Mono, monospace",
        "text-valign": "center",
        "text-halign": "center",
        color: "#f8fafc",
        width: "label",
        height: "label",
        padding: "12px",
        shape: "round-rectangle",
        "text-wrap": "wrap",
        "text-max-width": "140px",
        "border-width": 1,
        "border-color": "#334155",
      },
    },
    {
      selector: "edge",
      style: {
        width: (ele) => (ele.data("parallel") ? 2.5 : 1.5),
        "line-color": (ele) => (ele.data("parallel") ? "#fb923c" : "#64748b"),
        "target-arrow-color": (ele) => (ele.data("parallel") ? "#fb923c" : "#64748b"),
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.75,
        "curve-style": "bezier",
        "line-style": (ele) => (ele.data("parallel") ? "dashed" : "solid"),
      },
    },
    {
      selector: "node.highlighted",
      style: {
        "border-color": "#38bdf8",
        "border-width": 3,
      },
    },
  ];

  initCy(
    container,
    elements,
    {
      name: "dagre",
      rankDir: activeFlow === "query" ? "TB" : "LR",
      spacingFactor: 1.35,
    },
    style,
    () => {
      cy.one("layoutstop", () => cy.fit(undefined, 48));
      bindCyNodeHoverTips();
      cy.on("tap", "node", (evt) => {
        pauseFlowAnimation();
        updateFlowAnimButtons();
        const node = evt.target;
        const mid = node.id();
        document.querySelectorAll("#stepRail .step-item").forEach((el) => {
          el.classList.toggle("active", el.dataset.moduleId === mid);
        });
        const step = steps.find((s) => s.module_id === mid);
        if (step) pipelineStepInspector(step, steps.indexOf(step));
        cy.elements().removeClass("highlighted");
        node.addClass("highlighted");
        document.querySelectorAll("#flowSchematicHost .ph-box").forEach((box) => box.classList.remove("is-active"));
        document.querySelectorAll("#flowSchematicHost .flow-connector").forEach((p) => p.classList.remove("is-lit"));
        const cap = document.getElementById("flowPhaseCaption");
        if (cap) cap.textContent = "手动浏览图中节点；点击「播放」回到阶段动画。";
      });
      cy.on("tap", (evt) => {
        if (evt.target === cy) {
          pauseFlowAnimation();
          updateFlowAnimButtons();
          cy.elements().removeClass("highlighted");
          document.querySelectorAll("#flowSchematicHost .ph-box").forEach((box) => box.classList.remove("is-active"));
          document.querySelectorAll("#flowSchematicHost .flow-connector").forEach((p) => p.classList.remove("is-lit"));
          setInspector("pipeline", "管线详情", "<p>在左侧选择步骤、点击下方示意图阶段，或点击「播放」观看动画。</p>");
          const cap = document.getElementById("flowPhaseCaption");
          if (cap) cap.textContent = "点击「播放」或点击下方示意图阶段，查看右侧说明与图中高亮。";
        }
      });
    },
  );
}

function addPipeEdge(elements, source, target) {
  elements.push({
    data: { id: `${source}→${target}`, source, target },
  });
}

// ── MCP ──
function renderMcpView() {
  const proto = metadata.protocol || {};
  const tools = metadata.mcp_tools || [];

  document.getElementById("protoBanner").innerHTML = `
    <h2>协议与运行时</h2>
    <div class="proto-row">
      <span><strong>名称</strong> ${esc(proto.server_name || "?")}</span>
      <span><strong>版本</strong> ${esc(proto.server_version || "?")}</span>
      <span><strong>协议</strong> ${esc(proto.protocol_version || "?")}</span>
    </div>
    <div class="rpc-list">
      ${(proto.rpc_methods || [])
        .map(
          (r) =>
            `<div class="rpc-item"><span class="rpc-method">${esc(r.method)}</span> — ${esc(r.note || "")}</div>`,
        )
        .join("")}
    </div>`;

  document.getElementById("mcpGrid").innerHTML = tools.length
    ? tools
        .map((t) => {
          const schema = JSON.stringify(t.input_schema || {}, null, 2);
          const hm = t.handler_module ? `${esc(t.handler_module)}.${esc(t.handler_name || "")}` : "";
          return `<article class="tool-card">
          <h3>${esc(t.name)}</h3>
          ${hm ? `<div class="handler">${hm}</div>` : ""}
          <p class="desc">${esc(t.description)}</p>
          <div class="schema-pre">${esc(schema)}</div>
        </article>`;
        })
        .join("")
    : `<div class="card"><h2>无工具数据</h2><p>运行 <code>npm run parse</code> 重新生成 metadata。</p></div>`;
}
