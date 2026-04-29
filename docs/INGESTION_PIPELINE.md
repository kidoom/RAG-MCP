# IngestionPipeline 流水线架构

> 以 Apple 环境进展报告为例，追踪 PDF 从上传到可检索的全过程。

## 1. 总体架构

### 1.1 系统位置

IngestionPipeline 位于 **数据加工层**，向上承接文件上传入口，向下产出三类可检索资源。

```mermaid
graph TD
    subgraph 入口["Input"]
        direction LR
        A1["Dashboard UI"]
        A2["CLI scripts/ingest.py"]
        A3["Python API: pipeline.run()"]
    end

    入口 --> S1

    S1["<b>① Integrity</b><br/>SHA256(file) → file_hash<br/>SQLite: should_skip?<br/>重复 → skipped=True"]
    S1 -->|"new"| S2
    S1 -.->|"dup"| SKIP["Skipped"]

    S2["<b>② Load</b><br/>PdfLoader → pypdf<br/>输出: <b>Document</b><br/>├─ id (SHA256)<br/>├─ text + [IMAGE:xxx]<br/>└─ metadata.images[]"]
    S2 --> S3

    S3["<b>③ Split</b><br/>RecursiveCharacterSplitter<br/>chunk_size=1000 / overlap=200<br/>输出: List[<b>Chunk</b>]<br/>├─ id, text, metadata<br/>├─ chunk_index, source_ref<br/>└─ image_refs (按占位符分发)"]
    S3 --> S4

    S4["<b>④ Transform</b><br/>ChunkRefiner → MetadataEnricher → ImageCaptioner<br/>输出: List[<b>Chunk</b>] (refined)<br/>├─ metadata.title<br/>├─ metadata.summary<br/>├─ metadata.tags<br/>└─ metadata.image_captions (optional)"]
    S4 --> S5

    S5["<b>⑤ Encode</b><br/>DenseEncoder + SparseEncoder → BatchProcessor<br/>输出: List[<b>ChunkRecord</b>]<br/>├─ id, text, metadata<br/>├─ dense_vector[1024]<br/>└─ sparse_vector{terms, doc_length}"]
    S5 --> S6 & S7

    S6["<b>⑥ Store</b><br/>VectorUpserter: build_chunk_id() → ChromaDB.upsert<br/>BM25Indexer: rebuild=False → index.json<br/>collection 苹果公司 → encode → x_e88b..."]
    S7["<b>⑦ Image Store</b><br/>ImageStorage.save_image()<br/>→ data/images/苹果公司/<br/>→ image_index.db (ON CONFLICT)"]

    S6 --> VEC[("ChromaDB<br/>x_e88bb9e69e9c...<br/>72 vectors")]
    S6 --> BM25[("BM25<br/>index.json<br/>72 docs")]
    S7 --> IMG[("Images/<br/>苹果公司/<br/>120 png")]
    S7 --> IMGDB[("image_index.db<br/>120 rows")]

    S6 & S7 --> S8

    S8["<b>⑧ Finalize</b><br/>integrity.mark_success()<br/>trace.pipeline_done<br/>return <b>IngestionResult</b><br/>├─ skipped=False<br/>├─ doc_id<br/>├─ chunk_count=72<br/>├─ record_count=72<br/>└─ image_count=120"]

    VEC & BM25 & IMGDB --> DL["D 层 Retrieval<br/>HybridSearch<br/>DenseRetriever + SparseRetriever<br/>→ Reranker → ResponseBuilder"]
```

### 1.2 示例：Apple 环境报告

| 参数 | 值 |
|------|-----|
| 文件 | `Apple_Environmental_Progress_Report_2024.pdf` |
| 存入分类 | `苹果公司` |
| 文件规模 | 120 页，含 120 张图片 |
| 处理结果 | 切分为 72 个文本片段，全部存入向量库和关键词索引 |

### 1.3 数据流转总览

| 阶段 | 输入 | 输出 | 关键操作 |
|------|------|------|---------|
| ① Integrity | `file_path` | `file_hash` | `SHA256()` → `should_skip()` |
| ② Load | `file_path` | `Document` | `PdfLoader.load()` → `text` + `metadata.images[]` |
| ③ Split | `Document` | `List[Chunk]` | `RecursiveSplitter` + `DocumentChunker` → 稳定 `chunk_id` |
| ④ Transform | `List[Chunk]` | `List[Chunk]` | ChunkRefiner → MetadataEnricher → ImageCaptioner |
| ⑤ Encode | `List[Chunk]` | `List[ChunkRecord]` | DenseEncoder + SparseEncoder → `dense_vector` + `sparse_vector` |
| ⑥ Store | `List[ChunkRecord]` | ChromaDB + BM25 | `VectorUpserter.upsert()` + `BM25Indexer.build()` |
| ⑦ Image | `Document.metadata.images[]` | disk + SQLite | `ImageStorage.save_image()` → `ON CONFLICT UPDATE` |
| ⑧ Finalize | pipeline result | `IngestionResult` | `mark_success()` → `ingestion_history` |

### 1.4 存储产物

```
data/
├── db/
│   ├── chroma/                  ← ChromaDB: 向量集合 (collection = x_e88b...)
│   ├── bm25/index.json          ← BM25Indexer: 倒排索引 {term: {idf, postings[]}}
│   ├── image_index.db            ← ImageStorage: image_id PK, file_path, doc_hash, collection
│   └── ingestion_history.db      ← IntegrityChecker: file_hash PK, file_path, status, processed_at
├── images/
│   └── 苹果公司/                  ← 图片文件 (原始 collection 名)
│       └── {image_id}.png
└── logs/
    └── traces.jsonl              ← TraceContext 追踪日志
```

### 1.5 重复处理防护（四层幂等）

同一文件反复上传不会产生重复数据：

```mermaid
graph LR
    A["<b>Layer 1: file_integrity.py</b><br/>SHA256(file)<br/>→ ingestion_history.db<br/>should_skip() → True"] --> B["<b>Layer 2: vector_upserter.py</b><br/>build_chunk_id()<br/>SHA256(src|idx|content8)<br/>ChromaDB.upsert → UPDATE"]
    B --> C["<b>Layer 3: image_storage.py</b><br/>image_id PRIMARY KEY<br/>ON CONFLICT DO UPDATE<br/>→ overwrite"]
    C --> D["<b>Layer 4: bm25_indexer.py</b><br/>rebuild=False<br/>按 chunk_id 增量替换<br/>→ replace terms"]
```

| 层 | 文件 | 机制 | 效果 |
|----|------|------|------|
| 文件级 | file_integrity.py | `should_skip(file_hash)` 查 `ingestion_history.db` | 同文件跳过 pipeline |
| 向量级 | vector_upserter.py | `build_chunk_id()` 确定性 + `ChromaDB.upsert` | 同 chunk_id → UPDATE |
| 图片级 | image_storage.py | `image_id PK` + `ON CONFLICT DO UPDATE` | 同 image_id → 覆盖 |
| BM25 级 | bm25_indexer.py | `rebuild=False` 按 `chunk_id` 覆盖 | 同 id → 替换词项 |

## 2. 分阶段详解

### 2.1 ① Integrity — SHA256 文件校验

流程：计算文件指纹 → 查历史库 → 决定是否跳过。

```mermaid
graph TD
    A["file_path: Apple_..._2024.pdf"]
    B["compute_sha256(file)\n→ file_hash = 'e5042c0e...'"]
    C{"should_skip?<br/>SELECT status<br/>FROM ingestion_history<br/>WHERE file_hash = ?"}
    D["跳过\nreturn IngestionResult(skipped=True)"]
    E["继续\nreturn file_hash\n进入 Load"]

    A --> B --> C
    C -->|"status='success'"| D
    C -->|"not found / force=True"| E
```

- 数据表：`ingestion_history(file_hash PK, file_path, status, processed_at, error_msg)`
- `force=True` 可绕过跳过

**苹果文件**：首次上传，hash 不在库中 → 继续。

---

### 2.2 ② Load — PDF → Document

PdfLoader 调用 pypdf，逐页解析 PDF。

```mermaid
graph TD
    PDF["PDF: 120 pages"] --> T & I

    T["extract_text()\n逐页提取文字\n图片位置插 IMAGE:xxx 占位符"]
    I["extract_images()\n逐页提取图片为临时文件\n失败仅 log warning"]
    T & I --> V["validate_document_contract()\n校验 source_path, page_count"]

    V --> DOC["<b>Document</b>\nid = 'e5042c0e...' (SHA256)\ntext + [IMAGE:xxx] 占位符\nmetadata.page_count = 120\nmetadata.images[] = 120 项\n  ├─ id: 'img_001'\n  ├─ path: 临时文件路径\n  ├─ page: 页码\n  └─ position: 文字偏移"]
```

**苹果文件**：120 页文字 + 120 张图 → 1 个 Document。

---

### 2.3 ③ Split — Document → List[Chunk]

RecursiveCharacterSplitter 按 chunk_size=1000, overlap=200 切分，DocumentChunker 做适配。

```mermaid
graph TD
    DOC["Document"] --> SPLIT["RecursiveCharacterSplitter\nseparators: \\n\\n → \\n → ' ' → ''\n→ raw chunks"]

    SPLIT --> A1["1. 稳定 chunk_id\n'{doc_id}_{idx:04d}_{content_hash[:8]}'"]
    A1 --> A2["2. 继承 metadata\nsource_path, parent_doc_id, page_count"]
    A2 --> A3["3. chunk_index 编号"]
    A3 --> A4["4. source_ref = document.id"]
    A4 --> A5["5. 图片引用分发\n扫描 text 中 [IMAGE:x]\n只将本 chunk 引用的图附到 metadata"]
    A5 --> A6["6. 类型转换\nlibs.splitter.Chunk → core.types.Chunk"]

    A6 --> CHUNKS["List[<b>Chunk</b>] × 72\n每个 Chunk:\n├─ id: 'e504..._0025_a1b2c3d4'\n├─ text: '...solar farms in...'\n├─ metadata.source_path\n├─ metadata.parent_doc_id\n├─ metadata.chunk_index\n├─ metadata.images[] (按需)\n├─ metadata.image_refs[]\n├─ start_offset / end_offset\n└─ source_ref"]
```

**苹果文件**：~72 个 Chunk，含图片占位符的 Chunk 绑定了对应 `metadata.images[]`。

---

### 2.4 ④ Transform — ChunkRefiner → MetadataEnricher → ImageCaptioner

三次级联，每个遵循"规则兜底 + LLM 增强 + 降级标记"。

```mermaid
graph TD
    IN["List[Chunk] × 72"] --> R

    subgraph R["ChunkRefiner"]
        R1["规则: strip HTML · 去页眉页脚\n合并空白 · \\r\\n→\\n"]
        R2["LLM (可选): 调用 LLM 重写"]
        R3["输出: metadata.refined_by = 'rule' | 'llm'"]
    end

    R --> E
    subgraph E["MetadataEnricher"]
        E1["规则: title=首行(120) · summary=首400字\ntags=regex[A-Z]+CJK序列"]
        E2["LLM (可选): 语义生成 title/summary/tags"]
        E3["输出: metadata.title · metadata.summary\nmetadata.tags[] · metadata.enriched_by"]
    end

    E --> C
    subgraph C["ImageCaptioner"]
        C1["有 LLM + 有 image_refs:\nVision LLM → image_captions"]
        C2["无 LLM:\n保持 image_refs\nhas_unprocessed_images=True"]
    end

    C --> OUT["List[Chunk] × 72 (refined)\nmetadata 新增:\n├─ title, summary, tags\n├─ enriched_by, refined_by\n└─ image_captions (optional)"]
```

**苹果文件**：`use_llm: false`，只走规则路径。

---

### 2.5 ⑤ Encode — List[Chunk] → List[ChunkRecord]

BatchProcessor 将 Chunk 转为带向量的 ChunkRecord。

```mermaid
graph TD
    CHUNKS["List[Chunk] × 72"] --> BP

    subgraph BP["BatchProcessor (batch_size=100)"]
        SLICE["切片: 1 batch × 72"]
        DENSE["DenseEncoder.encode(texts)\nQwen text-embedding-v3\n→ List[float] × 1024"]
        SPARSE["SparseEncoder.encode(texts)\n分词+词频 → {terms, doc_length}"]
        DENSE & SPARSE --> MERGE["按 id 合并 dense+sparse\n验证: ID 匹配 + 数量一致"]
    end

    MERGE --> REC["List[<b>ChunkRecord</b>] × 72\n├─ id, text, metadata\n├─ dense_vector[1024]\n└─ sparse_vector\n    ├─ terms: {'solar': 1, ...}\n    └─ doc_length"]
```

**苹果文件**：72 < 100 → 1 批处理完。

---

### 2.6 ⑥ Store — ChromaDB + BM25 双重持久化

```mermaid
graph TD
    REC["List[ChunkRecord] × 72"] --> VS

    subgraph VS["VectorUpserter"]
        V1["encode_collection_name('苹果公司')\n→ 'x_e88bb9e69e9ce585ace58fb8'"]
        V2["build_chunk_id(record)\nSHA256(source_path|chunk_index|content_hash8)\n→ 87e86dbe8545c200..."]
        V3["ChromaDB.upsert(ids, embeddings, docs, metas)\n同 id UPDATE · 不同 id INSERT"]
    end

    VS --> CHROMA[("ChromaDB\nx_e88bb9e...\n72 vectors")]
    VS -->|"带稳定 chunk_id"| BM

    subgraph BM["BM25Indexer"]
        B1["提取 sparse_vector.terms"]
        B2["IDF: log((N-df+0.5)/(df+0.5))"]
        B3["倒排索引: {term: {idf, postings[]}}"]
        B4["persist → index.json"]
    end

    BM --> IDX[("BM25\nindex.json\n72 docs")]

    CHROMA --> S8
    IDX --> S8
```

**VectorUpserter must run before BM25**: 前者是 chunk_id 的权威来源（C12），BM25 接收相同 ID 保持命名空间一致。

---

### 2.7 ⑦ Image Store — 图片独立落盘

图片是文档级资源，独立于 Chunk 存储。

```mermaid
graph TD
    IMGS["Document.metadata.images[] × 120"] --> LOOP["for image in images:"]
    LOOP --> READ["读取临时文件 bytes"]
    READ --> SAVE["落盘: data/images/苹果公司/{image_id}.png"]
    READ --> UPSERT["SQLite upsert\nINSERT INTO image_index\n  (image_id PK, file_path, collection,\n   doc_hash, page_num, created_at)\nON CONFLICT(image_id) DO UPDATE"]

    SAVE --> DISK[("data/images/苹果公司/\n120 png")]
    UPSERT --> SQL[("image_index.db\n120 rows\n索引: idx_collection, idx_doc_hash")]
```

**苹果文件**：120 张图落盘 + 120 条 SQLite。

---

### 2.8 ⑧ Finalize — 标记完成

```mermaid
graph TD
    RESULT{"success?"}

    RESULT -->|"yes"| S1["integrity.mark_success(\n  file_hash, file_path,\n  'doc_id=...;chunks=72;records=72')"]
    S1 --> S2["trace.record_stage('pipeline_done')"]
    S2 --> S3["return <b>IngestionResult</b>\n├─ file_path\n├─ file_hash\n├─ skipped=False\n├─ doc_id\n├─ chunk_count=72\n├─ record_count=72\n└─ image_count=120"]

    RESULT -->|"exception"| F1["integrity.mark_failed(\n  file_hash, file_path, error)"]
    F1 --> F2["raise <b>IngestionPipelineError</b>\n├─ stage: 失败阶段名\n├─ file_path\n└─ message"]
```

**成功处理结果**：

```python
结果 = {
    "文件": "Apple_Environmental_Progress_Report_2024.pdf",
    "状态": "成功",
    "片段数": 72,
    "图片数": 120,
    "文档ID": "e5042c..."
}
```

---

## 3. 如何使用

### 页面操作

在 Dashboard 的 "Upload & Ingest" 页面：
1. 选择 PDF 文件
2. 填写集合名（如 `苹果公司`）
3. 点击开始
4. 实时进度条显示当前阶段
5. 完成后显示片段数和图片数

### 命令行

```bash
# 单个文件
python scripts/ingest.py --path docs/Apple.pdf --collection 苹果公司

# 整个目录
python scripts/ingest.py --path docs/ --collection knowledge_hub

# 强制重新处理
python scripts/ingest.py --path docs/Apple.pdf --force
```

### 代码调用

```python
from ingestion import IngestionPipeline
from core.settings import load_settings

pipeline = IngestionPipeline(load_settings())
result = pipeline.run("file.pdf", collection="my_collection")

# → IngestionResult:
#   result.skipped       # bool
#   result.doc_id        # Document.id (SHA256)
#   result.chunk_count   # len(List[Chunk])
#   result.record_count  # len(List[ChunkRecord])
#   result.image_count   # len(metadata.images[])
```

---

## 4. 关键文件

| 文件 | 作用 |
|------|------|
| [pipeline.py](src/ingestion/pipeline.py) | 流水线总控 |
| [document_chunker.py](src/ingestion/chunking/document_chunker.py) | 智能切片 |
| [chunk_refiner.py](src/ingestion/transform/chunk_refiner.py) | 文本清洗 |
| [metadata_enricher.py](src/ingestion/transform/metadata_enricher.py) | 标题/摘要/标签生成 |
| [batch_processor.py](src/ingestion/embedding/batch_processor.py) | 向量编码 |
| [vector_upserter.py](src/ingestion/storage/vector_upserter.py) | 向量存储 |
| [bm25_indexer.py](src/ingestion/storage/bm25_indexer.py) | 关键词索引 |
| [image_storage.py](src/ingestion/storage/image_storage.py) | 图片归档 |
| [document_manager.py](src/ingestion/document_manager.py) | 文档管理 |
| [pdf_loader.py](src/libs/loader/pdf_loader.py) | PDF 解析 |
| [file_integrity.py](src/libs/loader/file_integrity.py) | 文件去重 |
| [chroma_store.py](src/libs/vector_store/chroma_store.py) | 向量库 + 集合名编解码 |
| [settings.yaml](config/settings.yaml) | 全部配置 |

---

## 5. 配置速查

```yaml
ingestion:
  chunk_size: 1000          # 每个片段最大字符数
  chunk_overlap: 200        # 片段间重叠字符数
  splitter: "recursive"     # 切分策略
  batch_size: 100           # 编码批大小

embedding:
  provider: "qwen"
  model: "text-embedding-v3"
  dimensions: 1024          # 向量维度

vector_store:
  collection_name: "knowledge_hub"  # 默认集合名
```
