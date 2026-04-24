# B 站原始语料目录

## 文件

- `videos_corpus.jsonl`：视频元数据（`bvid`、标题、简介、播放量、`mid`、标签等），一行一条 JSON。

## 更新语料

在项目根目录或本 skill 目录下执行（**建议先设置 `NO_PROXY=*`**，避免错误代理）：

```bash
python scripts/fetch_bilibili_corpus.py --sleep 10 --max-pages 50
```

- 若频繁返回 HTML 或 `请求过于频繁`，拉大 `--sleep`，或隔一段时间再跑。  
- 全量覆盖官方全部投稿时，可适当增大 `--max-pages`（搜索分页上限以接口返回 `numPages` 为准）。

## 与 Nuwa 流程对齐

抓取完成后，应更新：

- `references/research/00-bilibili-corpus-summary.md`（统计与归纳）  
- `references/research/01~06.md`（把新证据按维度归档）  
- `SKILL.md`（刷新心智模型证据链与诚实边界）
