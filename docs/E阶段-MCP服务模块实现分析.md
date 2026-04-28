# E阶段：MCP Server 层与 Tools — 实现分析

> 版本：0.1.0 | 完成日期：2026-04-27 | 6/6 任务全部完成

---

## 1. E 阶段概述

E 阶段的目标是将 Modular RAG 系统封装为 **MCP（Model Context Protocol）标准服务**，通过 JSON-RPC 2.0 over stdio 暴露 3 个 tool，让 Copilot、Claude Desktop 等 AI 客户端可直接查询私有知识库。

### 1.1 任务清单

| 编号 | 任务 | 产出文件 | 状态 |
|------|------|---------|------|
| E1 | MCP Server 入口 + Stdio 约束 | [server.py](src/mcp_server/server.py) | [x] |
| E2 | JSON-RPC 协议处理器 | [protocol_handler.py](src/mcp_server/protocol_handler.py) | [x] |
| E3 | query_knowledge_hub 工具 | [query_knowledge_hub.py](src/mcp_server/tools/query_knowledge_hub.py) | [x] |
| E4 | list_collections 工具 | [list_collections.py](src/mcp_server/tools/list_collections.py) | [x] |
| E5 | get_document_summary 工具 | [get_document_summary.py](src/mcp_server/tools/get_document_summary.py) | [x] |
| E6 | 多模态响应组装 (Text+Image) | [multimodal_assembler.py](src/core/response/multimodal_assembler.py) | [x] |

### 1.2 前置依赖

E 阶段依赖于前序阶段已完成的能力：
- **阶段 C (Ingestion Pipeline)**：PDF 数据已被摄取、Embedding 已存入 ChromaDB、BM25 索引已构建
- **阶段 D (Retrieval)**：HybridSearch（Dense+Sparse+RRF Fusion）、Reranker 可正常调用

---

## 2. 项目文件结构

```
src/mcp_server/
└── server.py                         # E1: Stdio 入口，主循环，错误包装
└── protocol_handler.py               # E2: JSON-RPC 2.0 协议分发引擎
└── tools/
    ├── __init__.py                   # Tool 注册表，get_tool_specs()
    ├── query_knowledge_hub.py        # E3: 混合检索 + Reranker tool
    ├── list_collections.py           # E4: 列出文档集合 tool
    └── get_document_summary.py       # E5: 获取文档摘要 tool

src/core/response/                     # E3+E6: 响应层
├── __init__.py                       # 统一导出
├── response_builder.py               # E3: MCP 响应构建器
├── citation_generator.py             # E3: 引用生成器
└── multimodal_assembler.py           # E6: 多模态内容组装器

tests/
├── unit/test_protocol_handler.py     # E2: 协议处理器单元测试 (6 tests)
├── integration/test_mcp_server.py    # E1+E3+E6: 集成测试 (3 tests)
├── unit/test_response_builder.py     # E3: 响应构建器测试
├── unit/test_list_collections.py     # E4: 集合列表测试
├── unit/test_get_document_summary.py # E5: 文档摘要测试
└── unit/test_protocol_handler.py     # E2: 协议单元测试
```

---

## 3. 业务流 — MCP Server 对外提供什么能力

```
┌─────────────────────────────────────────────────────────┐
│                  MCP Client (Copilot/Claude)             │
│                           │ stdio JSON-RPC              │
│                           ▼                              │
│                  modular-rag-mcp-server                  │
│                                                         │
│  Tool 1: query_knowledge_hub                            │
│  "搜索知识库并返回带引用的答案"                             │
│  入参: query(必填), top_k(1-20), collection(可选)         │
│  出参: 文本引用 + 结构化 citations + 可选 base64 图像     │
│                                                         │
│  Tool 2: list_collections                               │
│  "列出可用文档集合"                                       │
│  入参: 无                                                │
│  出参: 集合名 + 文档数量统计                               │
│                                                         │
│  Tool 3: get_document_summary                           │
│  "获取单篇文档的标题/摘要/标签"                             │
│  入参: doc_id(必填), collection(可选)                     │
│  出参: title, summary(≤240chars), tags                   │
└─────────────────────────────────────────────────────────┘
```

**业务定位**：MCP Server 是系统的 **唯一外部接口**。客户端无需关心内部向量库、BM25 索引、Embedding 模型等细节，只需通过标准 JSON-RPC 协议调用这三个 tool 即可完成知识检索。

---

## 4. 数据流 — 完整的数据流转路径

```
================================================================================
                    data flow through the MCP server
================================================================================

 ┌────────────────── JSON-RPC Request (stdin, one line) ──────────────────┐
 │  {"jsonrpc":"2.0","id":1,"method":"tools/call",                        │
 │   "params":{"name":"query_knowledge_hub",                               │
 │             "arguments":{"query":"如何配置Azure","top_k":5}}}            │
 └────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  server.py: run_stdio_server()                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. sys.stdin.readline() → raw_line                                    │   │
│  │ 2. json.loads(line) → payload (ParseError → -32700)                   │   │
│  │ 3. protocol_handler.dispatch(payload)                                 │   │
│  │ 4. stdout.write(json.dumps(response) + "\n")                          │   │
│  │ 5. stdout.flush()                                                     │   │
│  │ ✅ stdout = only MCP messages, stderr = logs                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  protocol_handler.py: ProtocolHandler.dispatch()                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ method="initialize"  → handle_initialize(params)                      │   │
│  │   returns: {protocolVersion, serverInfo, capabilities}                │   │
│  │                                                                       │   │
│  │ method="tools/list"   → handle_tools_list()                           │   │
│  │   returns: {tools: [ToolSpec.to_dict() for each registered tool]}     │   │
│  │                                                                       │   │
│  │ method="tools/call"   → handle_tools_call(name, arguments)            │   │
│  │   name="query_knowledge_hub" → query_knowledge_hub(arguments)         │   │
│  │   name="list_collections"    → list_collections(arguments)            │   │
│  │   name="get_document_summary"→ get_document_summary(arguments)        │   │
│  │                                                                       │   │
│  │ id is None → Notification (no response, return None)                  │   │
│  │ unknown method → JsonRpcError(-32601)                                 │   │
│  │ invalid params  → JsonRpcError(-32602)                                │   │
│  │ tool crash      → JsonRpcError(-32603, "Internal error")              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ (query_knowledge_hub 为例)
┌─────────────────────────────────────────────────────────────────────────────┐
│  tools/query_knowledge_hub.py                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. Validate args (query/required, top_k/1-20, collection/optional)    │   │
│  │ 2. Load settings.yaml                                                 │   │
│  │ 3. Instantiate pipeline:                                              │   │
│  │      QueryProcessor → DenseRetriever + SparseRetriever                │   │
│  │                    → Fusion → HybridSearch → Reranker                  │   │
│  │ 4. hybrid.search(query, top_k, filters)                               │   │
│  │ 5. reranker.rerank(query, candidates, top_k)                          │   │
│  │ 6. ResponseBuilder.build(results, query)                             │   │
│  │                                                                       │   │
│  │ ⚠️ Graceful Degradation: any Exception → results = []                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  core/query_engine/hybrid_search.py: HybridSearch.search()                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. QueryProcessor.process(query, filters)                             │   │
│  │    → ProcessedQuery(normalized_query, keywords, filters)               │   │
│  │                                                                       │   │
│  │ 2. ThreadPoolExecutor(max_workers=2) parallel:                        │   │
│  │    ├─ DenseRetriever.retrieve(normalized_query, recall_k, filters)    │   │
│  │    │   └─ Embedding.embed([query]) → VectorStore.query(vector, k)     │   │
│  │    └─ SparseRetriever.retrieve(keywords, recall_k)                    │   │
│  │        └─ BM25Indexer.query(keywords, k) → get_by_ids(ids)            │   │
│  │                                                                       │   │
│  │ 3. if both succeed: Fusion.fuse(dense, sparse, recall_k) → RRF       │   │
│  │    elif one fails: use surviving results (single-path fallback)       │   │
│  │    elif both fail: raise RuntimeError                                │   │
│  │                                                                       │   │
│  │ 4. _apply_metadata_filters(candidates, filters) → post-filter        │   │
│  │ 5. return filtered[:top_k] → List[RetrievalResult]                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  core/query_engine/fusion.py: Fusion.fuse()                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ RRF_score(chunk_id) = SUM( 1 / (k + rank_position) )                  │   │
│  │   - k = settings.retrieval.rrf_k (default 60)                        │   │
│  │   - Accumulate scores from both dense and sparse rankings            │   │
│  │   - Sort by (-score, chunk_id) → deterministic                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  core/query_engine/reranker.py: Reranker.rerank()                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Loads Reranker from libs/reranker factory (LLM / Cross-Encoder / None)│   │
│  │ On failure/timeout → returns fusion order + metadata["fallback"]=True │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  core/response/response_builder.py: ResponseBuilder.build()                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. CitationGenerator.generate(results)                                │   │
│  │    → List[{source, page, chunk_id, score}]                            │   │
│  │                                                                       │   │
│  │ 2. _build_markdown(query, results)                                    │   │
│  │    → "查询：...\n\n检索结果：\n1. snippet... [1]\n   - source: ..."     │   │
│  │                                                                       │   │
│  │ 3. MultimodalAssembler.assemble(results)                              │   │
│  │    → Extract image_refs/images from metadata                          │   │
│  │    → ImageStorage.get_image_path(image_id)                            │   │
│  │    → base64 encode → [{type:"image", mimeType, data}]                 │   │
│  │                                                                       │   │
│  │ 4. Return:                                                            │   │
│  │    {"content": [text_block, *image_blocks],                            │   │
│  │     "structuredContent": {query, citations}}                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────── JSON-RPC Response (stdout, one line) ─────────────────┐
│  {"jsonrpc":"2.0","id":1,"result":{                                     │
│    "content":[                                                          │
│      {"type":"text","text":"查询：如何配置Azure\n\n检索结果：\n1. ..."},   │
│      {"type":"image","mimeType":"image/png","data":"iVBORw0K..."}       │
│    ],                                                                    │
│    "structuredContent":{                                                │
│      "query":"如何配置Azure",                                            │
│      "citations":[{"source":"azure.md","page":3,"chunk_id":"...",       │
│                     "score":0.92}]                                       │
│    }}}                                                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 功能流 — 三大 Tool 详解

### 5.1 Tool: `query_knowledge_hub` — 知识库混合检索

```
输入                      处理                             输出
─────────────────────────────────────────────────────────────────
query: "如何配置Azure"    → 参数校验 (query非空, top_k 1-20)
top_k: 5 (default)        → 加载 settings.yaml
collection: "" (optional) → 实例化检索管道
                           → HybridSearch.search()
                              ├─ QueryProcessor: 提取关键词+规范化
                              ├─ DenseRetriever: 语义向量检索 (并行)
                              ├─ SparseRetriever: BM25关键词检索 (并行)
                              └─ Fusion: RRF融合排序
                           → Reranker.rerank() (精细再排序)
                           → ResponseBuilder.build()
                              ├─ CitationGenerator: 结构化引用
                              ├─ _build_markdown: 可读文本
                              └─ MultimodalAssembler: 图像base64
                           → 返回 MCP content + structuredContent
                           
                           ⚠️ 异常降级: 整个管道异常时返回空结果
                           而非崩溃，确保tool始终可用

输出结构:
{
  "content": [
    {"type": "text", "text": "查询：...\n\n检索结果：\n1. snippet [1]\n   - source: ..."},
    {"type": "image", "mimeType": "image/png", "data": "<base64>"}  // 可选
  ],
  "structuredContent": {
    "query": "...",
    "citations": [{"source": "...", "page": 5, "chunk_id": "...", "score": 0.92}]
  }
}
```

**关键设计点**：
- **双路并行召回**：Dense + Sparse 通过 `ThreadPoolExecutor(max_workers=2)` 并行执行
- **单路降级**：Dense 或 Sparse 任一路失败时，自动回退到存活的结果路径
- **全链路降级**：整个 `try/except Exception` 包裹检索链路，任何异常都返回空列表而非 500
- **recall_k = top_k × 2**：扩大召回池，确保融合+过滤后还有足够候选项

### 5.2 Tool: `list_collections` — 列出文档集合

```
输入              处理                              输出
──────────────────────────────────────────────────────────
(无参数)          → 读取 data/documents/ 目录
                  → 遍历子目录 (sorted by name)
                  → 统计每个子目录的文件数 (rglob)
                  → 构建 Markdown + structuredContent
                  
                  如果 documents/ 不存在 → 返回空集合列表

输出结构:
{
  "content": [{"type": "text", "text": "可用集合：\n1. knowledge_hub (5 files)"}],
  "structuredContent": {"collections": [{"name": "knowledge_hub", "document_count": 5}]}
}
```

**关键设计点**：
- 纯文件系统操作，无外部依赖
- 支持 `_documents_root` 参数覆盖默认路径（用于测试）
- 空目录返回友好提示 "暂无可用集合"

### 5.3 Tool: `get_document_summary` — 获取文档摘要

```
输入                               处理                            输出
─────────────────────────────────────────────────────────────────────────
doc_id: "chunk-abc123"             → 参数校验 (doc_id非空)
collection: "" (optional)          → 加载 settings.yaml
                                   → VectorStoreFactory.create()
                                   → vector_store.get_by_ids([doc_id])
                                   → 提取 metadata:
                                      - title (优先 metadata.title → 
                                        回退 source_path 文件名)
                                      - summary (截断到 240 字符)
                                      - tags (列表规范化)
                                   → 文档不存在 → ValueError "doc_id not found"
                                   → 存在 → 构建结构化响应

输出结构:
{
  "content": [{"type": "text", "text": "Azure配置指南\n\n本文介绍如何在...（截断）..."}],
  "structuredContent": {"doc_id": "chunk-abc123", "title": "Azure配置指南", 
                        "summary": "本文介绍如何在...", "tags": ["azure", "配置"]}
}
```

**关键设计点**：
- `doc_id` 不存在时抛出 `ValueError` → ProtocolHandler 映射为 `-32602` (Invalid params)
- title 回退链：`metadata.title → metadata.source_path → source → doc_id`
- summary 截断到 240 字符 + "..."（防止响应过大）
- tags 支持字符串和列表两种输入格式，自动规范化

---

## 6. 调用流 — 请求/响应生命周期

### 6.1 完整调用时序

```
MCP Client                server.py              ProtocolHandler          Tool Handler
    │                        │                         │                       │
    │──JSON-RPC Request────▶│                         │                       │
    │   (stdin line)        │                         │                       │
    │                        │──json.loads(line)──────│                       │
    │                        │──dispatch(payload)────▶│                       │
    │                        │                         │──method routing──    │
    │                        │                         │                      │
    │                        │      ┌──────────────────┼──────────────┐       │
    │                        │      │ initialize       │ tools/list   │       │
    │                        │      │ → handle_init()  │ → handle_    │       │
    │                        │      │                  │   tools_list()│       │
    │                        │      │ tools/call       │              │       │
    │                        │      │ → handle_tools_  │              │       │
    │                        │      │   call(name,args)│──────────────▶       │
    │                        │      │                  │              │       │
    │                        │      │                  │   tool.handler(args) │
    │                        │      │                  │◀─────────────────────│
    │                        │      │                  │   result dict        │
    │                        │      ├──────────────────┤                      │
    │                        │      │ {"jsonrpc":"2.0",│                      │
    │                        │      │  "id":id,        │                      │
    │                        │      │  "result":result}│                      │
    │                        │◀─────│                  │                      │
    │                        │      │                  │                      │
    │──JSON-RPC Response────▶│      │                  │                      │
    │   (stdout line)        │      │                  │                      │
    │                        │      │                  │                      │
```

### 6.2 三种标准 MCP 方法

| 方法 | 触发时机 | 请求参数 | 响应内容 |
|------|---------|---------|---------|
| `initialize` | 客户端首次连接 | `protocolVersion`, `clientInfo`, `capabilities` | `protocolVersion`, `serverInfo:{name,version}`, `capabilities:{tools:{}}` |
| `tools/list` | 客户端发现工具 | 无 | `tools: [{name, description, inputSchema}, ...]` |
| `tools/call` | 客户端调用工具 | `name`, `arguments` | 取决于具体 tool (见 5.1-5.3) |

### 6.3 JSON-RPC 错误码体系

| 错误码 | 含义 | 触发场景 | 处理位置 |
|--------|------|---------|---------|
| `-32700` | Parse error | 输入不是合法 JSON | [server.py:38-43](src/mcp_server/server.py#L38) |
| `-32600` | Invalid Request | payload 非 dict / 无 method | [protocol_handler.py:88](src/mcp_server/protocol_handler.py#L88) |
| `-32601` | Method not found | 未知 method / 未注册的 tool 名 | [protocol_handler.py:73](src/mcp_server/protocol_handler.py#L73) + [line 120](src/mcp_server/protocol_handler.py#L120) |
| `-32602` | Invalid params | 参数类型错误 / 必填参数缺失 / tool 抛出 ValueError | [protocol_handler.py:52](src/mcp_server/protocol_handler.py#L52) + [line 66-78](src/mcp_server/protocol_handler.py#L66) |
| `-32603` | Internal error | Tool handler 内部异常（原始错误不泄露到响应中） | [server.py:51](src/mcp_server/server.py#L51) + [protocol_handler.py:83](src/mcp_server/protocol_handler.py#L83) |

**安全设计**：`-32603` 内部错误绝不泄露原始堆栈信息，仅返回 "Internal error" 给客户端，原始异常通过 stderr 日志记录。

### 6.4 Notification 处理

当请求中无 `id` 字段时，视为 JSON-RPC **Notification**：
- `ProtocolHandler.dispatch()` 返回 `None`
- `server.py` 跳过响应写入（`if response is None: continue`）
- 客户端不期望收到任何响应

---

## 7. 核心组件详解

### 7.1 `server.py` — Stdio 传输层

```
职责：
  - 读取 stdin → 解析 JSON → 分发 → 写回 stdout
  - 日志只写 stderr（保证 stdout 只输出 MCP 消息）
  - 三类异常捕获：ParseError / JsonRpcError / 未知 Exception
  - 空行跳过（支持协议健壮性）

关键约束：
  - stdout: 只输出 JSON-RPC 响应（严格单行 JSON）
  - stderr: 所有日志（通过 get_logger 写入）
  - 主循环: for raw_line in sys.stdin → 惰性读取，无超时
  - 响应格式: json.dumps(response, ensure_ascii=True) + "\n"
```

### 7.2 `protocol_handler.py` — JSON-RPC 协议引擎

```
ProtocolHandler 类:
  ├── _tools: dict[str, ToolSpec]  # tool名 → tool规范索引
  │
  ├── handle_initialize(params)    # 能力协商
  │   └── 返回: protocolVersion + serverInfo + capabilities.tools
  │
  ├── handle_tools_list()          # 工具发现
  │   └── 返回: [ToolSpec.to_dict() for each tool]
  │
  ├── handle_tools_call(name, args)# 工具路由
  │   ├── 校验: name非空且已注册 / arguments为dict或None
  │   ├── 路由: spec.handler(arguments)
  │   ├── ValueError/TypeError → -32602
  │   ├── JsonRpcError → 透传
  │   └── 其他Exception → -32603 (不泄露原始错误信息)
  │
  └── dispatch(payload)            # 总入口
      ├── payload非dict → -32600
      ├── method缺失 → -32600
      ├── id缺失 → Notification (return None)
      ├── method="initialize" → handle_initialize()
      ├── method="tools/list"  → handle_tools_list()
      ├── method="tools/call"  → handle_tools_call()
      └── 其他 → -32601

ToolSpec (frozen dataclass):
  - name: str          # "query_knowledge_hub"
  - description: str   # "Search the knowledge hub..."
  - input_schema: dict # {"type":"object","properties":{...},"required":[...]}
  - handler: Callable  # Python callable
  - to_dict()          # 序列化为 MCP 标准 tool schema

JsonRpcError(Exception):
  - code: int          # JSON-RPC error code
  - message: str       # 人类可读错误描述
```

### 7.3 Tool 注册表 — `tools/__init__.py`

```python
get_tool_specs() → list[ToolSpec]:
  [
    ToolSpec(
      name="query_knowledge_hub",
      description="Search the knowledge hub and return cited answers.",
      input_schema={"type":"object","properties":{"query":{"type":"string"},...},"required":["query"]},
      handler=query_knowledge_hub
    ),
    ToolSpec(name="list_collections", ...),
    ToolSpec(name="get_document_summary", ...),
  ]
```

添加新 tool 的流程：只需在此函数中追加一个新的 `ToolSpec`，无需修改 `server.py` 或 `protocol_handler.py`。

### 7.4 Response Layer — 响应构建管道

```
ResponseBuilder
  ├── CitationGenerator.generate(results) → List[citation]
  │   └── 从 RetrievalResult.metadata 提取 source_path/source, page, chunk_id, score
  │
  ├── _build_markdown(query, results) → str
  │   ├── 无结果: "未找到相关文档，请先运行 ingest.py 摄取数据。"
  │   ├── 有结果: 格式化为 "查询：<q>\n\n检索结果：\n1. snippet [1]\n   - source: ..."
  │   └── snippet截断: text[:180] + "..."
  │
  └── MultimodalAssembler.assemble(results) → List[image_content]
      ├── 提取 image_refs (metadata.image_refs / metadata.images)
      ├── 去重 (seen set)
      ├── ImageStorage.get_image_path(image_id)
      ├── base64.b64encode(path_obj.read_bytes())
      └── 返回 [{type:"image", mimeType:"image/png", data:"<base64>"}]
```

---

## 8. 依赖关系全景图

```
                          MCP SERVER LAYER (E阶段)
                          ====================
                          server.py
                            │ import
                          protocol_handler.py
                            │ import
                          tools/__init__.py
                         ┌──┼──────────────┐
                         │  │              │
            query_       list_        get_document_
        knowledge_hub  collections     summary
              │              │              │
              ▼              │              ▼
     ┌──────────────┐       │       ┌──────────────┐
     │ CORE LAYER   │       │       │ LIBS LAYER   │
     │ (D+E阶段)    │       │       │ VectorStore  │
     │              │       │       │ Factory      │
     │ QueryProcessor      │       └──────────────┘
     │ DenseRetriever      │
     │ SparseRetriever     │
     │ Fusion (RRF)        │
     │ HybridSearch        │
     │ Reranker            │
     │ ResponseBuilder     │
     │ CitationGenerator   │
     │ MultimodalAssembler │
     └──────┬──────────────┘
            │
     ┌──────┴──────────────────────────────────────┐
     │ LIBS LAYER (B阶段)                          │
     │                                             │
     │ EmbeddingFactory → BaseEmbedding            │
     │   ├── OpenAIEmbedding                       │
     │   ├── QwenEmbedding                         │
     │   ├── GeminiEmbedding                       │
     │   └── ...7 providers                        │
     │                                             │
     │ VectorStoreFactory → BaseVectorStore        │
     │   └── ChromaStore                           │
     │                                             │
     │ RerankerFactory → BaseReranker              │
     │   ├── LLMReranker                           │
     │   ├── CrossEncoderReranker                  │
     │   └── NoneReranker                          │
     │                                             │
     │ LLMFactory → BaseLLM / BaseVisionLLM        │
     │                                             │
     │ INGESTION LAYER (C阶段, 离线链路)            │
     │   └── ImageStorage (SQLite + WAL)           │
     └─────────────────────────────────────────────┘
```

---

## 9. 测试体系

### 9.1 测试矩阵

| 测试文件 | 测试数 | 类型 | 覆盖范围 |
|---------|--------|------|---------|
| [test_protocol_handler.py](tests/unit/test_protocol_handler.py) | 6 | unit | initialize / tools/list / tools/call / 错误码 / 内部错误不泄露 |
| [test_response_builder.py](tests/unit/test_response_builder.py) | N | unit | ResponseBuilder / CitationGenerator / Markdown格式 |
| [test_list_collections.py](tests/unit/test_list_collections.py) | N | unit | 目录存在/不存在 / 文件计数 / structuredContent |
| [test_get_document_summary.py](tests/unit/test_get_document_summary.py) | N | unit | doc_id存在/不存在 / title回退 / summary截断 / tags规范化 |
| [test_mcp_server.py](tests/integration/test_mcp_server.py) | 3 | integration | 子进程initialize / query_knowledge_hub端到端 / 多模态图像返回 |

### 9.2 关键测试能力

- **子进程测试**：`test_mcp_server.py` 通过 `subprocess.Popen` 启动真实 server 进程，通过 stdin/stdout 管道发送/接收 JSON-RPC 消息
- **mock 隔离**：单元测试使用 mock EmbeddingClient / mock VectorStore / mock LLM，不依赖外部服务
- **安全验证**：`test_dispatch_tool_internal_error_returns_32603` 验证内部异常堆栈不泄露到错误消息中
- **多模态**：`test_response_builder_includes_image_content` 用假 PNG 数据验证 base64 编码和 mimeType

---

## 10. 关键设计决策总结

| 决策 | 理由 |
|------|------|
| **Stdio 而非 HTTP** | MCP 标准要求；无需端口配置/防火墙/CORS |
| **stderr 日志隔离** | 保证 stdout 只输出 JSON-RPC，客户端解析不受日志干扰 |
| **全链路异常降级** | query_knowledge_hub 即使检索完全失败也返回空结果，不阻断 client 交互 |
| **RRF k=60 可配置** | k 值控制排名融合的平滑度，60 是经典默认值 |
| **recall_k = top_k × 2** | 给融合和后置过滤留出余量，避免最终结果不足 |
| **内部错误不泄露** | -32603 统一返回 "Internal error"，防止泄露系统细节 |
| **ToolSpec frozen dataclass** | 不可变设计防止运行时意外修改 tool schema |
| **双路并行 + 降级** | ThreadPoolExecutor 并行执行 Dense/Sparse，单路失败不影响另一路 |
| **ID 确定性回退链** | get_document_summary 的 title 从 metadata.title → source_path → source → doc_id 逐级回退 |

---

## 11. 扩展指南 — 如何添加新 Tool

在现有架构中添加新 MCP tool 只需 3 步：

1. **创建 tool handler 文件** `src/mcp_server/tools/your_new_tool.py`
   ```python
   def your_new_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
       # 实现 tool 逻辑
       return {"content": [...], "structuredContent": {...}}
   ```

2. **在 `tools/__init__.py` 注册**
   ```python
   from .your_new_tool import your_new_tool
   
   def get_tool_specs():
       return [
           ...existing tools...,
           ToolSpec(name="your_new_tool", description="...",
                    input_schema={...}, handler=your_new_tool),
       ]
   ```

3. **编写测试** `tests/unit/test_your_new_tool.py`

无需修改 `server.py` 或 `protocol_handler.py`。
