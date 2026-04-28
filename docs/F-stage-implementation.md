# 阶段 F：Trace 基础设施与打点 — 完整实现文档

> **完成日期**：2026-04-27  
> **状态**：5/5 任务完成，38 个测试全通过  
> **依赖**：阶段 C（Ingestion Pipeline）、阶段 D（Retrieval）、阶段 E（MCP Server）

---

## 一、任务总览

| 任务 | 名称 | 修改/新增文件 | 测试 |
|------|------|--------------|------|
| F1 | TraceContext 增强 | `src/core/trace/trace_context.py`、`trace_collector.py` | `test_trace_context.py` (12 tests) |
| F2 | JSON Lines 结构化日志 | `src/observability/logger.py` | `test_jsonl_logger.py` (5 tests) |
| F3 | Query 链路打点 | `src/core/query_engine/hybrid_search.py`、`reranker.py` | `test_hybrid_search.py` + `test_reranker_fallback.py` (11 tests) |
| F4 | Ingestion 链路打点 | `src/ingestion/pipeline.py` | `test_ingestion_pipeline.py` (5 tests) |
| F5 | Pipeline 进度回调 | `src/ingestion/pipeline.py` | `test_pipeline_progress.py` + `test_ingestion_pipeline.py` (8 tests) |

---

## 二、任务流 (Task Flow)

```
┌─────────────────────────────────────────────────────────────┐
│                    F Stage Task Flow                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐    ┌──────┐  │
│  │ F1   │───▶│ F2   │───▶│ F3   │───▶│ F4   │───▶│ F5   │  │
│  │Trace │    │JSON  │    │Query │    │Ingst │    │Prog. │  │
│  │Ctx   │    │Logger│    │Trace │    │Trace │    │CB    │  │
│  └──┬───┘    └──┬───┘    └──┬───┘    └──┬───┘    └──┬───┘  │
│     │           │           │           │           │       │
│     ▼           ▼           ▼           ▼           ▼       │
│  finish()    JSONLines   HybridSearch  Pipeline     on_     │
│  elapsed_ms  write_trace  Reranker     _stage_*     progress│
│  to_dict()   JSONFormatter record_     elapsed_ms   callback│
│  TraceColl.               stage()      method                │
└─────────────────────────────────────────────────────────────┘
```

**依赖链**：
- F1 (TraceContext 数据结构) → F2/F3/F4/F5 的全部依赖
- F2 (日志持久化) → F3/F4 使用 `write_trace()` 持久化 trace
- F3 (Query 打点) → 依赖 F1，修改 HybridSearch + Reranker
- F4 (Ingestion 打点) → 依赖 F1，修改 IngestionPipeline
- F5 (进度回调) → 依赖 F4，在同一个 Pipeline 类中添加

---

## 三、工作流 (Workflow)

### 3.1 开发工作流

```
1. F1: 增强 TraceContext 数据结构
   ├── 添加 started_at / finished_at 时间戳
   ├── 添加 finish() 方法
   ├── 添加 elapsed_ms(stage_name?) 方法
   ├── 增强 to_dict() 输出所有字段
   └── 新增 TraceCollector 收集器

2. F2: 实现 JSON Lines 结构化日志
   ├── JSONFormatter (logging.Formatter 子类)
   ├── get_trace_logger() (专用 trace logger)
   ├── write_trace() (持久化到 logs/traces.jsonl)
   └── 验证 JSON 合法性 + 多行追加

3. F3: Query 链路打点
   ├── HybridSearch.search() 接入 TraceContext
   │   ├── query_processing 阶段
   │   ├── dense_retrieval 阶段 (并行)
   │   ├── sparse_retrieval 阶段 (并行)
   │   └── fusion 阶段 (仅双路成功时)
   ├── Reranker.rerank() 接入 TraceContext
   │   └── rerank 阶段 (含 fallback 标记)
   └── 更新测试断言 trace stage 存在性

4. F4: Ingestion 链路打点
   ├── Pipeline 各 _stage_* 方法添加 elapsed_ms
   ├── 各阶段添加 method 字段
   │   ├── integrity: "sha256+sqlite"
   │   ├── load: Loader 类名
   │   ├── split: settings.ingestion.splitter
   │   ├── encode: "{embedding.provider}+bm25"
   │   └── store: settings.vector_store.provider
   └── 更新测试断言

5. F5: Pipeline 进度回调
   ├── 定义 ProgressCallback 类型别名
   ├── IngestionPipeline.run() 添加 on_progress 参数
   ├── 每个阶段调用 _fire(on_progress, stage, current, total)
   └── on_progress=None 时不影响现有行为
```

### 3.2 运行时工作流 (Query 链路)

```
用户发起查询
    │
    ▼
HybridSearch.search(query, top_k, filters, trace=TraceContext("query"))
    │
    ├─[t0]─ QueryProcessor.process()
    │         trace.record_stage("query_processing", method="rule", ...)
    │
    ├─[t1]─ ThreadPoolExecutor ─┬─ DenseRetriever.retrieve()
    │                            └─ SparseRetriever.retrieve()
    │         trace.record_stage("dense_retrieval", method=provider, ...)
    │         trace.record_stage("sparse_retrieval", method="bm25", ...)
    │
    ├─[t2]─ Fusion.fuse() [if both succeed]
    │         trace.record_stage("fusion", method="rrf", ...)
    │
    ├─[t3]─ Reranker.rerank(candidates, trace=trace)
    │         trace.record_stage("rerank", method=backend, fallback=..., ...)
    │
    ▼
返回 List[RetrievalResult]
    │
    ▼
trace.finish() → trace.to_dict() → write_trace() → logs/traces.jsonl
```

### 3.3 运行时工作流 (Ingestion 链路)

```
Pipeline.run(file_path, collection, trace=TraceContext("ingestion"), on_progress=cb)
    │
    ├─ on_progress("integrity", 0, 1)
    ├─ _stage_integrity() → trace.record_stage("integrity", elapsed_ms, method="sha256+sqlite")
    │
    ├─ on_progress("load", 0, 1)
    ├─ _stage_load() → trace.record_stage("load", elapsed_ms, method=LoaderClass)
    ├─ on_progress("load", 1, 1)
    │
    ├─ on_progress("split", 0, estimate)
    ├─ _stage_split() → trace.record_stage("split", elapsed_ms, method=splitter)
    ├─ on_progress("split", n, n)
    │
    ├─ on_progress("transform", i, total) [per transform step]
    ├─ _stage_transform() → trace.record_stage("transform_step", ...) + trace.record_stage("transform", ...)
    ├─ on_progress("transform", total, total)
    │
    ├─ on_progress("encode", 0, len)
    ├─ _stage_encode() → trace.record_stage("encode", elapsed_ms, method="openai+bm25")
    ├─ on_progress("encode", n, n)
    │
    ├─ on_progress("store", 0, len)
    ├─ _stage_store() → trace.record_stage("store", elapsed_ms, method="chroma")
    ├─ on_progress("store", n, n)
    │
    ├─ _stage_store_images() → trace.record_stage("image_store", elapsed_ms)
    │
    ▼
trace.finish() → write_trace() → logs/traces.jsonl
```

---

## 四、数据流 (Data Flow)

### 4.1 TraceContext 数据结构

```python
TraceContext:
    trace_type: str          # "query" | "ingestion"
    trace_id: str            # UUID4
    _started_at: float       # time.monotonic() at init
    _finished_at: float|None # time.monotonic() at finish()
    _stages: List[Dict]      # 阶段记录列表

# 阶段记录条目结构
{
    "stage": str,            # 阶段名
    "timestamp": float,      # time.monotonic()
    "elapsed_ms": float,     # 该阶段耗时（毫秒）
    "method": str,           # 使用的provider/method
    ...                      # 其他阶段特定字段
}

# to_dict() 输出结构
{
    "trace_id": "uuid-...",
    "trace_type": "query" | "ingestion",
    "started_at": 1714200000.0,
    "finished_at": 1714200001.0,
    "total_elapsed_ms": 1000.0,
    "stages": [
        {"stage": "query_processing", "timestamp": ..., "elapsed_ms": ..., "method": "rule", ...},
        {"stage": "dense_retrieval",  "timestamp": ..., "elapsed_ms": ..., "method": "openai", ...},
        ...
    ]
}
```

### 4.2 数据流向图

```
┌──────────────────────────────────────────────────────────────┐
│                      DATA FLOW MAP                           │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  [Query 入口]                    [Ingestion 入口]             │
│     │                                 │                       │
│     ▼                                 ▼                       │
│  HybridSearch                    IngestionPipeline            │
│  .search()                       .run()                       │
│     │                                 │                       │
│     │ trace.record_stage()            │ trace.record_stage()  │
│     ▼                                 ▼                       │
│  ┌─────────────────────────────────────────────┐             │
│  │           TraceContext (in-memory)           │             │
│  │  _stages: [                                 │             │
│  │    {stage, timestamp, elapsed_ms, method},  │             │
│  │    ...                                      │             │
│  │  ]                                          │             │
│  └──────────────────┬──────────────────────────┘             │
│                     │                                         │
│                     │ trace.finish()                          │
│                     │ trace.to_dict()                         │
│                     ▼                                         │
│  ┌─────────────────────────────────────────────┐             │
│  │          TraceCollector.collect()            │             │
│  │  - calls trace.finish()                     │             │
│  │  - calls on_collect(data) callback          │             │
│  └──────────────────┬──────────────────────────┘             │
│                     │                                         │
│                     ▼                                         │
│  ┌─────────────────────────────────────────────┐             │
│  │        observability.logger.write_trace()    │             │
│  │  - json.dumps(trace_dict)                   │             │
│  │  - append to logs/traces.jsonl              │             │
│  │  - emit via get_trace_logger() (stderr)      │             │
│  └──────────────────┬──────────────────────────┘             │
│                     │                                         │
│                     ▼                                         │
│  ┌─────────────────────────────────────────────┐             │
│  │         logs/traces.jsonl (持久化)           │             │
│  │  每行一个 JSON 对象，追加写入               │             │
│  │  {"trace_id":"...","trace_type":"query",...} │             │
│  │  {"trace_id":"...","trace_type":"ingest",...}│             │
│  └─────────────────────────────────────────────┘             │
│                                                               │
│  [下游消费]                                                   │
│  - Dashboard G5: Ingestion 追踪页面                          │
│  - Dashboard G6: Query 追踪页面                              │
│  - TraceService: 解析 traces.jsonl                           │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 Query Trace Stages 数据契约

| stage | method | elapsed_ms | 关键字段 |
|-------|--------|-----------|---------|
| `query_processing` | `"rule"` | ✓ | `keywords`, `filters` |
| `dense_retrieval` | `"{embedding_provider}"` | ✓ | `result_count`, `error` |
| `sparse_retrieval` | `"bm25"` | ✓ | `result_count`, `error` |
| `fusion` | `"rrf"` | - | `rrf_k`, `candidate_count` |
| `rerank` | `"{rerank_provider}"` | ✓ | `fallback`, `fallback_reason` |

### 4.4 Ingestion Trace Stages 数据契约

| stage | method | elapsed_ms | 关键字段 |
|-------|--------|-----------|---------|
| `integrity` | `"sha256+sqlite"` | ✓ | `file_hash`, `force`, `skipped` |
| `load` | `"{Loader类名}"` | ✓ | `doc_id`, `text_chars` |
| `split` | `"{splitter_provider}"` | ✓ | `chunk_count` |
| `transform` | - | ✓ | `chunk_count` |
| `transform_step` | `"{Transform类名}"` | ✓ | `transform`, `chunk_count` |
| `encode` | `"{embedding_provider}+bm25"` | ✓ | `record_count` |
| `store` | `"{vector_store_provider}"` | ✓ | `record_count` |
| `image_store` | - | ✓ | `stored_count` |
| `pipeline_done` | - | - | `file_path`, `doc_id`, 等 |

---

## 五、执行调用关系 (Execution Call Graph)

### 5.1 F1 — TraceContext 增强

```
test_trace_context.py (12 tests)
  ├── test_trace_context_has_trace_type_field
  │     └── TraceContext(trace_type="query") → assert trace_type
  ├── test_trace_context_default_trace_type
  │     └── TraceContext() → assert "ingestion"
  ├── test_trace_context_stores_started_at
  │     └── TraceContext() → to_dict()["started_at"]
  ├── test_record_stage_includes_timestamp
  │     └── ctx.record_stage("load", doc_id="d1") → stages[0]["timestamp"]
  ├── test_finish_sets_finished_at
  │     └── ctx.finish() → to_dict()["finished_at"]
  ├── test_finish_is_idempotent
  │     └── ctx.finish() ×2 → same finished_at
  ├── test_elapsed_ms_total
  │     └── ctx.finish() → ctx.elapsed_ms() >= 0.0
  ├── test_elapsed_ms_for_named_stage
  │     └── ctx.record_stage("load") → ctx.elapsed_ms("load")
  ├── test_elapsed_ms_unknown_stage_returns_zero
  │     └── ctx.elapsed_ms("nonexistent") == 0.0
  ├── test_to_dict_json_serializable
  │     └── json.dumps(ctx.to_dict()) 不抛异常
  ├── test_to_dict_contains_required_keys
  │     └── to_dict() 包含 trace_id/trace_type/started_at/finished_at/total_elapsed_ms/stages
  └── test_trace_collector_finishes_and_stores_trace
        └── TraceCollector(on_collect=cb).collect(ctx) → traces[0] 已 finish
```

### 5.2 F2 — JSON Lines 日志

```
test_jsonl_logger.py (5 tests)
  ├── test_json_formatter_produces_valid_json
  │     └── JSONFormatter().format(LogRecord) → json.loads(line)
  ├── test_json_formatter_includes_exception
  │     └── JSONFormatter().format(ERROR record) → "exception" in data
  ├── test_get_trace_logger_outputs_json
  │     └── get_trace_logger().info(...) → StringIO → json.loads
  ├── test_write_trace_writes_json_line_to_file
  │     └── write_trace(dict, file_path) → Path.read_text → json.loads
  └── test_write_trace_appends_multiple_lines
        └── write_trace() ×2 → 2 lines in file
```

### 5.3 F3 — Query 链路打点

```
HybridSearch.search(query, top_k, filters, trace=TraceContext("query"))
  │
  ├── QueryProcessor.process(query, filters) → ProcessedQuery
  │     └── trace.record_stage("query_processing",
  │           method="rule",
  │           elapsed_ms=(t_qp - t_start) * 1000,
  │           keywords=[...], filters={...})
  │
  ├── [并行] DenseRetriever.retrieve(normalized_query, recall_k, filters, trace)
  │     └── trace.record_stage("dense_retrieval",
  │           method=self._settings.embedding.provider,  # e.g. "openai"
  │           result_count=len(results),
  │           error=bool(error),
  │           elapsed_ms=(t_retrieval - t_qp) * 1000)
  │
  ├── [并行] SparseRetriever.retrieve(keywords, recall_k, trace)
  │     └── trace.record_stage("sparse_retrieval",
  │           method="bm25",
  │           result_count=len(results),
  │           error=bool(error),
  │           elapsed_ms=(t_retrieval - t_qp) * 1000)
  │
  ├── Fusion.fuse(dense, sparse, recall_k) [if both succeed]
  │     └── trace.record_stage("fusion",
  │           method="rrf",
  │           rrf_k=settings.retrieval.rrf_k,
  │           candidate_count=len(candidates))
  │
  └── Reranker.rerank(query, candidates, top_k, trace)
        ├── [成功] trace.record_stage("rerank",
        │     method=backend_name,
        │     fallback=False,
        │     elapsed_ms=...)
        └── [失败/降级] trace.record_stage("rerank",
              method=backend_name,
              fallback=True,
              fallback_reason=str(exc),
              elapsed_ms=...)
```

### 5.4 F4 — Ingestion 链路打点

```
IngestionPipeline.run(file_path, collection, force, trace=TraceContext("ingestion"))
  │
  ├── _stage_integrity()
  │     └── trace.record_stage("integrity",
  │           elapsed_ms=(time.monotonic() - t0) * 1000,
  │           method="sha256+sqlite",
  │           file_hash=..., force=..., skipped=...)
  │
  ├── _stage_load()
  │     └── trace.record_stage("load",
  │           elapsed_ms=...,
  │           method=LoaderClassName,
  │           doc_id=..., text_chars=...)
  │
  ├── _stage_split()
  │     └── trace.record_stage("split",
  │           elapsed_ms=...,
  │           method=settings.ingestion.splitter,  # e.g. "recursive"
  │           chunk_count=...)
  │
  ├── _stage_transform()
  │     ├── [per transform step] trace.record_stage("transform_step",
  │     │     transform=ClassName,
  │     │     chunk_count=...,
  │     │     elapsed_ms=...)
  │     └── trace.record_stage("transform",
  │           elapsed_ms=...,
  │           chunk_count=...)
  │
  ├── _stage_encode()
  │     └── trace.record_stage("encode",
  │           elapsed_ms=...,
  │           method="{embedding.provider}+bm25",  # e.g. "openai+bm25"
  │           record_count=...)
  │
  ├── _stage_store()
  │     └── trace.record_stage("store",
  │           elapsed_ms=...,
  │           method=settings.vector_store.provider,  # e.g. "chroma"
  │           record_count=...)
  │
  ├── _stage_store_images()
  │     └── trace.record_stage("image_store",
  │           elapsed_ms=...,
  │           stored_count=...)
  │
  └── trace.record_stage("pipeline_done", ...)
```

### 5.5 F5 — 进度回调

```
ProgressCallback = Callable[[str, int, int], None]
#                          stage  current total

IngestionPipeline.run(file_path, ..., on_progress=callback)
  │
  ├── _fire(on_progress, "integrity", 0, 1)
  ├── _stage_integrity()
  │
  ├── _fire(on_progress, "load", 0, 1)
  ├── _stage_load()
  ├── _fire(on_progress, "load", 1, 1)
  │
  ├── _fire(on_progress, "split", 0, estimate)
  ├── _stage_split()
  ├── _fire(on_progress, "split", len(chunks), len(chunks))
  │
  ├── _fire(on_progress, "transform", 0, len(transforms))
  ├── ... [per transform]
  ├── _fire(on_progress, "transform", len(transforms), len(transforms))
  │
  ├── _fire(on_progress, "encode", 0, len(chunks))
  ├── _stage_encode()
  ├── _fire(on_progress, "encode", len(records), len(records))
  │
  ├── _fire(on_progress, "store", 0, len(records))
  ├── _stage_store()
  └── _fire(on_progress, "store", len(stored), len(stored))
```

---

## 六、功能实现详情

### 6.1 F1：TraceContext 增强

**文件**：[`src/core/trace/trace_context.py`](src/core/trace/trace_context.py)

```python
@dataclass
class TraceContext:
    trace_type: str = "ingestion"        # "query" | "ingestion"
    trace_id: str = uuid4()              # 唯一标识
    _stages: List[Dict] = []             # 阶段记录
    _started_at: float = monotonic()     # 构造时间
    _finished_at: float | None = None    # 完成时间

    def record_stage(name, **details):
        """记录一个阶段，自动附加 timestamp"""
        self._stages.append({"stage": name, "timestamp": monotonic(), **details})

    def finish():
        """标记 trace 完成（幂等）"""

    def elapsed_ms(stage_name=None) -> float:
        """获取指定阶段或整体耗时（毫秒）"""

    def to_dict() -> dict:
        """序列化为 JSON-safe 字典，包含 started_at/finished_at/total_elapsed_ms/stages"""
```

**设计决策**：
- 使用 `time.monotonic()` 而非 `time.time()`：不受系统时钟调整影响，确保耗时计算准确
- `finish()` 幂等：多次调用不会重复设置 `_finished_at`
- `elapsed_ms()` 双模式：无参数返回总耗时，传入 stage 名返回该阶段从开始到记录的耗时
- `to_dict()` 始终可调用，即使未 finish（`finished_at` 为 null）

**新增文件**：[`src/core/trace/trace_collector.py`](src/core/trace/trace_collector.py)

```python
class TraceCollector:
    """收集完成的 TraceContext 并可通过回调持久化"""
    def collect(trace: TraceContext):
        trace.finish()
        data = trace.to_dict()
        self._traces.append(data)
        if self._on_collect:
            self._on_collect(data)
```

### 6.2 F2：JSON Lines 结构化日志

**文件**：[`src/observability/logger.py`](src/observability/logger.py)

```python
class JSONFormatter(logging.Formatter):
    """输出 JSON 格式日志：{timestamp, level, logger, message, exception?}"""

def get_trace_logger(name="trace") -> logging.Logger:
    """获取专用 trace logger，JSON Lines 输出到 stderr"""

def write_trace(trace_dict: dict, file_path=None):
    """将 trace dict 追加写入 logs/traces.jsonl + stderr 日志"""
```

**设计决策**：
- JSON Lines 格式（每行一个 JSON 对象）：易于 `tail -f`、`jq` 和日志聚合工具解析
- `write_trace()` 自动创建 `logs/` 目录
- 主 logger 保持 plain text 格式（stderr），trace logger 独立使用 JSON 格式
- `propagate=False` 防止 trace 日志重复输出到 root logger

### 6.3 F3：Query 链路打点

**修改文件**：

1. [`src/core/query_engine/hybrid_search.py`](src/core/query_engine/hybrid_search.py) — `HybridSearch.search()` 方法
   - 添加 `time.monotonic()` 计时点
   - 在 query_processing / dense_retrieval / sparse_retrieval / fusion 阶段调用 `trace.record_stage()`
   - 仅当 `trace is not None` 时记录（向后兼容）
   - fusion 阶段仅在双路都成功时记录

2. [`src/core/query_engine/reranker.py`](src/core/query_engine/reranker.py) — `Reranker.rerank()` 方法
   - 添加 rerank 阶段 trace 记录
   - 区分成功（`fallback=False`）和降级（`fallback=True` + `fallback_reason`）
   - 参数类型从 `Optional[Any]` 改为 `Optional[TraceContext]`

**关键实现细节**：
- dense_retrieval 和 sparse_retrieval 并行执行，共享同一个计时区间
- 当仅单路成功时，不记录 fusion 阶段
- 每个 stage 包含 `elapsed_ms`、`method`、`result_count`/`error` 字段

### 6.4 F4：Ingestion 链路打点

**修改文件**：[`src/ingestion/pipeline.py`](src/ingestion/pipeline.py)

在所有 `_stage_*` 方法中添加：
- `t0 = time.monotonic()` 计时起始
- `elapsed_ms=(time.monotonic() - t0) * 1000.0` 耗时字段
- `method=...` 标识使用的具体实现

各阶段 method 取值：
| 阶段 | method 来源 |
|------|-----------|
| integrity | 固定 `"sha256+sqlite"` |
| load | `loader.__class__.__name__` |
| split | `settings.ingestion.splitter` |
| encode | `f"{settings.embedding.provider}+bm25"` |
| store | `settings.vector_store.provider` |

### 6.5 F5：Pipeline 进度回调

**修改文件**：[`src/ingestion/pipeline.py`](src/ingestion/pipeline.py)

```python
ProgressCallback = Callable[[str, int, int], None]
# on_progress(stage_name, current, total)

def run(self, ..., on_progress: Optional[ProgressCallback] = None):
    _fire(on_progress, "integrity", 0, 1)
    # ...
    _fire(on_progress, "load", 0, 1)
    document = self._stage_load(...)
    _fire(on_progress, "load", 1, 1)
    # ...
```

**辅助函数**：
```python
def _fire(on_progress, stage, current, total):
    """安全调用进度回调（None 时 no-op）"""
    if on_progress is not None:
        on_progress(stage, current, total)

def _estimate_chunk_count(document):
    """在 split 前估算 chunk 数量用于进度条"""
```

**设计决策**：
- 回调签名 `(stage, current, total)`：与 Streamlit `st.progress()` 的语义对齐
- 使用 `_fire()` 辅助函数避免分散的 `if on_progress is not None` 检查
- `_estimate_chunk_count()` 提供 split 阶段的 total 估算
- `on_progress=None` 时零开销（仅一次 None 检查跳过）

---

## 七、文件变更清单

### 新增文件

| 文件 | 用途 |
|------|------|
| `src/core/trace/trace_collector.py` | TraceCollector - 收集并持久化 trace |
| `tests/unit/test_trace_context.py` | F1 单元测试 (12 tests) |
| `tests/unit/test_jsonl_logger.py` | F2 单元测试 (5 tests) |
| `tests/unit/test_pipeline_progress.py` | F5 单元测试 (5 tests) |

### 修改文件

| 文件 | 变更内容 |
|------|---------|
| `src/core/trace/trace_context.py` | 添加 started_at/finished_at、finish()、elapsed_ms()、增强 to_dict() |
| `src/core/trace/__init__.py` | 添加 TraceCollector 导出 |
| `src/observability/logger.py` | 添加 JSONFormatter、get_trace_logger()、write_trace() |
| `src/core/query_engine/hybrid_search.py` | search() 添加 4 阶段 trace 记录 |
| `src/core/query_engine/reranker.py` | rerank() 添加 trace 记录 + 类型收紧 |
| `src/ingestion/pipeline.py` | 所有 stage 添加 elapsed_ms/method；添加 on_progress 参数；新增 _fire/_estimate_chunk_count |
| `tests/integration/test_hybrid_search.py` | 添加 2 个 trace 验证测试 + Settings 增加 embedding/rerank 字段 |
| `tests/unit/test_reranker_fallback.py` | 添加 2 个 trace 验证测试 |
| `tests/integration/test_ingestion_pipeline.py` | 添加 3 个 F4/F5 验证测试 |

---

## 八、测试覆盖矩阵

| 测试文件 | 测试数 | 覆盖任务 |
|---------|--------|---------|
| `test_trace_context.py` | 12 | F1: finish/elapsed_ms/to_dict/TraceCollector |
| `test_jsonl_logger.py` | 5 | F2: JSONFormatter/write_trace/get_trace_logger |
| `test_hybrid_search.py` | 5 (2 new) | F3: Query trace stages |
| `test_reranker_fallback.py` | 6 (2 new) | F3: Reranker trace success/fallback |
| `test_ingestion_pipeline.py` | 5 (3 new) | F4: elapsed_ms/method; F5: on_progress |
| `test_pipeline_progress.py` | 5 | F5: ProgressCallback/fire/estimate |

**合计**：38 个 F 阶段相关测试，全部通过。

---

## 九、与后续阶段的接口

### 阶段 G 使用方式

```python
# G5: Ingestion 追踪页面
from observability.dashboard.services.trace_service import TraceService
service = TraceService()
traces = service.list_traces(trace_type="ingestion")
for t in traces:
    stages = t["stages"]
    # 渲染瀑布图：load/split/transform/encode/store 的 elapsed_ms

# G6: Query 追踪页面
traces = service.list_traces(trace_type="query")
for t in traces:
    # 渲染 Dense vs Sparse 对比 + Rerank 前后排名变化

# G4: Ingestion 管理页面
pipeline.run(file_path, collection, on_progress=lambda s, c, t: st.progress(c/t, f"{s}: {c}/{t}"))
```

### Trace 文件格式约定

- 路径：`{REPO_ROOT}/logs/traces.jsonl`
- 格式：每行一个 JSON 对象（`json.dumps(trace.to_dict())`，`ensure_ascii=False`）
- 写入：追加模式（`open(path, "a")`），自动创建父目录
- 消费：`TraceService` 读取全部行 → `json.loads(line)` → 按 `trace_type` 过滤
