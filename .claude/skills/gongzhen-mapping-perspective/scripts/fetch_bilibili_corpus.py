#!/usr/bin/env python3
"""
抓取 B 站公开视频元数据（标题、BV 号、播放量、发布时间等），写入 JSONL。
优先使用系统 curl（Windows 下 Python urllib 常被 412）；搜索 API 分页 + 按 mid 过滤。

用法:
  NO_PROXY=* python fetch_bilibili_corpus.py [--sleep SEC] [--max-pages N]

环境:
  需要 PATH 中有 curl（Windows 10+ 自带）。
  建议设置 NO_PROXY=*，避免错误代理导致 SSL/连接失败。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
SPACE_ARC_URL = "https://api.bilibili.com/x/space/arc/search"

CURL_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def strip_em_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r'<em class="keyword">', "", s)
    s = s.replace("</em>", "")
    return s


def curl_get_json(url: str, referer: str, retries: int = 4, base_sleep: float = 8.0) -> dict:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("未找到 curl，请安装或将 curl 加入 PATH")
    args = [
        curl,
        "-sS",
        url,
        "-H",
        f"User-Agent: {CURL_UA}",
        "-H",
        f"Referer: {referer}",
    ]
    last_err: Exception | None = None
    for attempt in range(retries):
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
        if proc.returncode != 0:
            last_err = RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
        else:
            text = proc.stdout
            if text.lstrip().startswith("<!DOCTYPE"):
                last_err = RuntimeError("HTML response")
            else:
                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    last_err = e
        time.sleep(base_sleep * (attempt + 1))
    raise RuntimeError(f"curl_get_json failed after {retries} tries: {last_err}")


def fetch_search_page(keyword: str, page: int) -> dict:
    from urllib.parse import urlencode

    qs = urlencode(
        {"search_type": "video", "keyword": keyword, "page": page},
        encoding="utf-8",
    )
    url = f"{SEARCH_URL}?{qs}"
    return curl_get_json(url, "https://www.bilibili.com/")


def fetch_space_page(mid: int, pn: int, ps: int = 30) -> dict:
    from urllib.parse import urlencode

    qs = urlencode(
        {"mid": mid, "pn": pn, "ps": ps, "order": "pubdate", "tid": 0, "keyword": ""},
        encoding="utf-8",
    )
    url = f"{SPACE_ARC_URL}?{qs}"
    return curl_get_json(url, f"https://space.bilibili.com/{mid}")


def iter_videos_for_mid(keyword: str, mid: int, sleep_s: float, max_pages: int | None):
    seen: set[str] = set()
    page = 1
    while True:
        if max_pages is not None and page > max_pages:
            break
        data = fetch_search_page(keyword, page)
        if data.get("code") != 0:
            raise RuntimeError(f"API error: {data}")
        result = data.get("data", {}).get("result") or []
        if not result:
            break
        for item in result:
            if item.get("mid") != mid:
                continue
            bvid = item.get("bvid")
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)
            yield {
                "bvid": bvid,
                "aid": item.get("id"),
                "title": strip_em_html(item.get("title") or ""),
                "description": strip_em_html(item.get("description") or ""),
                "author": item.get("author"),
                "mid": item.get("mid"),
                "pubdate": item.get("pubdate"),
                "play": item.get("play"),
                "like": item.get("like"),
                "duration": item.get("duration"),
                "tag": item.get("tag"),
            }
        num_pages = int(data.get("data", {}).get("numPages") or 1)
        if page >= num_pages:
            break
        page += 1
        time.sleep(sleep_s)


def iter_space_videos(mid: int, sleep_s: float, max_pages: int | None):
    seen: set[str] = set()
    pn = 1
    ps = 30
    while True:
        if max_pages is not None and pn > max_pages:
            break
        data = fetch_space_page(mid, pn, ps)
        if data.get("code") != 0:
            raise RuntimeError(f"space API: {data}")
        vlist = data.get("data", {}).get("list", {}).get("vlist") or []
        if not vlist:
            break
        for item in vlist:
            bvid = item.get("bvid")
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)
            yield {
                "bvid": bvid,
                "aid": item.get("aid"),
                "title": item.get("title") or "",
                "description": item.get("description") or "",
                "author": item.get("author"),
                "mid": mid,
                "pubdate": item.get("created"),
                "play": item.get("play"),
                "like": None,
                "duration": None,
                "tag": None,
            }
        if len(vlist) < ps:
            break
        pn += 1
        time.sleep(sleep_s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleep", type=float, default=10.0, help="分页间隔秒数（越大越不容易触发风控）")
    ap.add_argument("--max-pages", type=int, default=None, help="每个数据源最多翻页数（调试用）")
    ap.add_argument(
        "--out",
        default="references/sources/bilibili/videos_corpus.jsonl",
        help="相对 skill 根目录的输出路径",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 同一 mid 可配置多个搜索词，合并去重（覆盖标题里不一定出现账号昵称的稿件）
    targets = [
        {"mid": 483099804, "keywords": ["幻鲨文化SKGPLUS"]},
        {
            "mid": 1093978385,
            "keywords": [
                "龚震Mapping",
                "光影展为何大众不买单",
                "创业十年的心得和感受",
            ],
        },
    ]

    all_rows: list[dict] = []
    for idx, t in enumerate(targets):
        if idx:
            time.sleep(25)
        mid = t["mid"]
        for kwi, kw in enumerate(t["keywords"]):
            if kwi:
                time.sleep(12)
            try:
                for row in iter_videos_for_mid(kw, mid, args.sleep, args.max_pages):
                    row["fetch_method"] = "search"
                    row["source_keyword"] = kw
                    all_rows.append(row)
            except Exception as e:
                print(f"[warn] search failed for kw={kw!r} mid={mid}: {e}", file=sys.stderr)
                try:
                    for row in iter_space_videos(mid, args.sleep, args.max_pages):
                        row["fetch_method"] = "space_arc"
                        row["source_keyword"] = kw
                        all_rows.append(row)
                except Exception as e2:
                    print(f"[error] space failed mid={mid}: {e2}", file=sys.stderr)

    # bvid 去重（优先保留 search 行）
    by_bvid: dict[str, dict] = {}
    for row in all_rows:
        b = row.get("bvid")
        if not b:
            continue
        if b not in by_bvid or row.get("fetch_method") == "search":
            by_bvid[b] = row
    merged = list(by_bvid.values())
    merged.sort(key=lambda r: (r.get("pubdate") is None, r.get("pubdate") or 0))

    with open(out_path, "w", encoding="utf-8") as f:
        for row in merged:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"written {len(merged)} unique videos -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
