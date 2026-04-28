# IngestionPipeline 流水线架构

> 以 Apple 环境进展报告为例，追踪 PDF 从上传到可检索的全过程。

## 1. 总体架构

### 1.1 系统位置

IngestionPipeline 位于 **数据加工层**，向上承接文件上传入口，向下产出三类可检索资源。

```mermaid
graph TD
    subgraph 入口["　📥 文件上传入口　"]
        direction LR
        A1["📄 页面上传 PDF / TXT / MD"]
        A2["💻 命令行批量导入目录"]
        A3["🐍 Python API 调用"]
    end

    入口 --> S1

    subgraph S1_["　"]
        S1["<b>第一步</b><br/>文件校验<br/>──<br/>计算 SHA256 指纹<br/>查历史数据库<br/>判断是否重复"]
    end

    S1 -->|"首次上传"| S2
    S1 -.->|"重复文件"| SKIP["⏭ 直接跳过<br/>返回成功"]

    subgraph S2_["　"]
        S2["<b>第二步</b><br/>内容解析<br/>──<br/>pypdf 逐页提取文字<br/>图片插入占位标记<br/>组装为结构化文档"]
    end

    S2 --> DOC["<b>📄 Document</b><br/>全文 + 120 张图片信息<br/>document_id = e5042c..."]

    subgraph S3_["　"]
        S3["<b>第三步</b><br/>智能切片<br/>──<br/>按段落 → 行 → 空格逐级切<br/>每段 ≤ 1000 字 · 重叠 200 字<br/>生成确定性片段编号"]
    end

    DOC --> S3

    S3 --> C{"<b>~72 个 Chunk</b><br/>每个含文本 + 元数据<br/>有图的 Chunk 绑定对应图片"}

    subgraph S4_["　"]
        S4["<b>第四步</b><br/>信息增强<br/>──<br/>① 清洗格式噪音<br/>② 生成标题 / 摘要 / 标签<br/>③ 视觉 AI 理解图片（可选）"]
    end

    C --> S4

    S4 --> C2["<b>72 个精炼 Chunk</b><br/>文本干净 · 有标题摘要 · 有标签"]

    subgraph S5_["　"]
        S5["<b>第五步</b><br/>向量编码<br/>──<br/>语义编码：文字 → 1024 维向量<br/>关键词统计：分词 + 词频<br/>两者按 ID 合并为一条记录"]
    end

    C2 --> S5

    S5 --> REC["<b>72 条 ChunkRecord</b><br/>语义向量 · 关键词 · 原文"]

    REC --> S6 & S7

    subgraph S6_["　"]
        S6["<b>第六步</b><br/>分类存储<br/>──<br/>存入语义向量库<br/>（集合名苹果公司 → 编码为 x_e88b...）<br/>构建关键词倒排索引"]
    end

    subgraph S7_["　"]
        S7["<b>第七步</b><br/>图片归档<br/>──<br/>120 张图落盘<br/>目录：data/images/苹果公司/<br/>写入 SQLite 图片索引"]
    end

    S6 --> VEC[("　🗄️ ChromaDB 向量库<br/>x_e88bb9... 集合<br/>72 条向量记录　")]
    S6 --> BM25[("　📇 BM25 关键词索引<br/>index.json<br/>72 条倒排索引　")]
    S7 --> IMG[("　🖼️ 图片资源<br/>data/images/苹果公司/<br/>120 个 png 文件　")]
    S7 --> IMGDB[("　🗃️ 图片索引<br/>image_index.db<br/>120 条记录　")]

    VEC & BM25 --> S8
    IMG & IMGDB --> S8

    subgraph S8_["　"]
        S8["<b>第八步</b><br/>完成标记<br/>──<br/>写入历史数据库<br/>记录成功状态<br/>返回处理结果"]
    end

    S8 --> RESULT["<b>✅ IngestionResult</b><br/>文件: Apple_..._2024.pdf<br/>状态: 成功 · 72 片段 · 120 图片"]

    VEC --> 检索
    BM25 --> 检索
    IMGDB --> 检索

    subgraph 检索["　🔍 检索服务消费　"]
        direction LR
        R1["语义搜索<br/>相似含义匹配"]
        R2["关键词搜索<br/>精确词匹配"]
        R3["混合搜索<br/>语义 + 关键词"]
        R4["多模态回答<br/>引用图片"]
    end
```

### 1.2 示例：Apple 环境报告

| 参数 | 值 |
|------|-----|
| 文件 | `Apple_Environmental_Progress_Report_2024.pdf` |
| 存入分类 | `苹果公司` |
| 文件规模 | 120 页，含 120 张图片 |
| 处理结果 | 切分为 72 个文本片段，全部存入向量库和关键词索引 |

### 1.3 流水线全貌

```mermaid
graph TD
    A["上传 PDF 文件\n120 页 · 120 张图"]:::start

    B["第一步：文件校验\n计算文件指纹 · 判断是否重复\n首次上传 → 继续处理"]:::stage
    C["第二步：内容解析\n提取文字 · 提取图片\n→ 得到原始文档"]:::stage
    D["第三步：智能切片\n按段落/行/空格逐级切分\n→ 约 72 个文本片段"]:::stage
    E["第四步：信息增强\n清洗格式 · 生成标题摘要\n→ 质量更高的片段"]:::stage
    F["第五步：向量编码\n将文字转为数学向量\n→ 机器可理解的表示"]:::stage
    G["第六步：分类存储\n语义向量库 + 关键词索引\n→ 可被搜索"]:::stage
    H["第七步：图片归档\n图片落盘 · 建立索引\n→ 120 张图可被引用"]:::stage
    I["第八步：完成标记\n记录处理状态\n下次同一文件自动跳过"]:::finish

    A --> B --> C --> D --> E --> F --> G & H
    G & H --> I

    classDef start fill:#e1f5fe
    classDef stage fill:#fff
    classDef finish fill:#c8e6c9
```

### 1.4 处理后的产物

```
data/
├── db/
│   ├── chroma/              ← 语义向量（机器搜索用）
│   ├── bm25/index.json      ← 关键词索引（关键词搜索用）
│   ├── image_index.db        ← 图片索引（找图用）
│   └── ingestion_history.db  ← 处理记录（避免重复处理）
├── images/
│   └── 苹果公司/             ← 图片原文件
└── logs/
    └── traces.jsonl          ← 处理日志
```

### 1.5 重复处理防护（四层幂等）

同一文件反复上传不会产生重复数据：

```mermaid
graph LR
    A["第一道防线\n文件指纹比对\n指纹相同 → 直接跳过"] --> B["第二道防线\n片段编号唯一\n同编号 → 覆盖不新增"]
    B --> C["第三道防线\n图片编号唯一\n同编号 → 覆盖不重复"]
    C --> D["第四道防线\n关键词增量更新\n同编号 → 替换旧数据"]
```

| 防线 | 判断依据 | 效果 |
|------|---------|------|
| 文件级 | SHA256 文件指纹 | 同文件不重复处理 |
| 向量级 | 确定性片段编号 | 同片段覆盖写入 |
| 图片级 | 图片唯一主键 | 同图片覆盖不重复 |
| 关键词级 | 按片段编号增量 | 同编号替换旧词条 |

## 2. 分阶段详解

### 2.1 第一步：文件校验

拿到 PDF 后，先算一个"文件指纹"（SHA256），去数据库里查：这个文件处理过没？

```mermaid
graph TD
    A["收到 PDF 文件"] --> B["计算文件指纹\n类似给文件拍一张\n独一无二的数字照片"]
    B --> C{"查历史记录\n这个指纹见过吗？"}
    C -->|"见过且成功"| D["跳过处理\n直接返回"]
    C -->|"没见过/之前失败"| E["进入下一步\n开始解析内容"]
```

**苹果文件**：首次上传，指纹不在历史中 → 继续。

---

### 2.2 第二步：内容解析

把 PDF 变成程序能理解的格式。

```mermaid
graph TD
    A["PDF 文件\n120 页"] --> B["逐页读取文字\n图片位置插入标记"]
    A --> C["逐页提取图片\n保存为临时文件"]
    B & C --> D["组装为结构化文档\n文字 + 图片标记 + 图片信息"]
    D --> E["校验完整性\n确保必要字段齐全"]
```

**产出**：一个结构化文档对象，包含：
- 全文文本（图片处有 `[IMAGE: 编号]` 标记）
- 120 张图片的信息（编号、位置、所在页码）

**苹果文件**：120 页全部提取成功。

---

### 2.3 第三步：智能切片

一整本书太长，切成小段才好搜索。

```mermaid
graph TD
    A["完整文档\n一整本书"] --> B["按段落边界切分\n（优先用空行）"]
    B --> C["还太长？按行切"]
    C --> D["还太长？按句切"]
    D --> E["每段不超过 1000 字\n段与段之间有 200 字重叠\n保证上下文不断裂"]
    E --> F["每个片段做好标记\n来源文件 · 序号 · 包含的图片"]
```

**额外处理**：
- 每个片段生成唯一编号，同一文件永远产生同样编号
- 检测每个片段里有没有图片标记，有就把对应图片信息附上

**苹果文件**：120 页 → 约 **72 个片段**。

---

### 2.4 第四步：信息增强

原始切出来的片段比较粗糙，做三道加工。

```mermaid
graph TD
    A["72 个原始片段"] --> B["第一道：清洗\n去掉格式噪音\n去掉页眉页脚\n规整换行空白"]
    B --> C["第二道：充实\n提取标题\n生成摘要\n打上标签"]
    C --> D["第三道：识图\n（可选）用视觉AI\n理解图片内容\n生成图片描述"]
    D --> E["72 个精炼片段\n干净 · 有标题 · 有标签"]
```

**第一道 — 清洗**：
- 去除 PDF 提取时产生的格式垃圾（HTML 标签、多余空白等）
- 可选择调用大模型进一步润色（生产环境通常关闭）

**第二道 — 充实**：
- 标题：取片段第一行
- 摘要：取片段前 400 字
- 标签：自动提取关键词（如 `environmental`, `report`, `apple`）

**第三道 — 识图**（可选）：
- 如有图片且开启了视觉 AI，自动生成图片描述

**苹果文件**：当前设置未开启 AI 增强，只做规则清洗和自动标签。

---

### 2.5 第五步：向量编码

把人类文字转成数学向量，机器才能做语义搜索。

```mermaid
graph TD
    A["72 个精炼片段"] --> B["分批处理\n每 100 个一批"]
    B --> C["语义编码\n将文字含义压缩为\n1024 个数字的向量"]
    B --> D["关键词统计\n统计词频\n记录词出现次数"]
    C & D --> E["合并为一个数据记录\n语义向量 + 关键词 + 原文"]
```

**通俗理解**：语义向量就像一个"意义地图"，意思相近的句子在地图上挨得近。

**苹果文件**：72 个片段 < 100 → 一批处理完。

---

### 2.6 第六步：分类存储

将向量和关键词分别存入两个库。

```mermaid
graph TD
    A["72 条数据记录"] --> B["存语义向量\n到向量数据库\n（用集合名作为分类）"]
    A --> C["建关键词索引\n到倒排索引文件\n（类似书的目录）"]
    B --> D[("语义向量库\n72 条记录")]
    C --> E[("关键词索引\n72 条记录")]
```

**关于"集合名"（Collection）**：

用户上传时填的集合名（如 `苹果公司`）就是分类标签。由于向量数据库只支持英文命名，中文名会被自动编码：

```
用户填：苹果公司
   ↓ 编码
向量库存：x_e88bb9e69e9c...
   ↓ 解码（显示时）
页面显示：苹果公司
```

这个编解码过程对用户完全透明，页面始终显示中文名。

**苹果文件**：72 条记录全部存入 `苹果公司` 分类。

---

### 2.7 第七步：图片归档

图片单独存储，不跟文本混在一起。

```mermaid
graph TD
    A["120 张待归档图片"] --> B["逐张处理\n读临时文件"]
    B --> C["复制到图片目录\n按集合名分类存放"]
    B --> D["写入图片索引\n记录：编号 · 路径 · 所属文档 · 页码"]
    C --> E[("data/images/苹果公司/\n120 个图片文件")]
    D --> F[("image_index.db\n120 条索引")]
```

**为什么分开存**：一个图片可能被多个片段引用，分开管理更方便删除和迁移。

**苹果文件**：120 张图全部归档。

---

### 2.8 第八步：完成标记

记录处理结果，确保下次不重复劳动。

```mermaid
graph TD
    A{"处理结果？"}
    A -->|"全部成功"| B["记录成功\n写入历史数据库\n文件指纹 + 成功状态"]
    A -->|"任何环节出错"| C["记录失败\n写入历史数据库\n文件指纹 + 失败状态"]
    B --> D["返回结果摘要\n72 个片段 · 120 张图片 · 处理成功"]
    C --> E["抛出错误\n标明失败环节\n下次可重试"]
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
print(f"片段: {result.chunk_count}, 图片: {result.image_count}")
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
