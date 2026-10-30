"""Bounded read-only paper sources and citation provenance for research runs."""
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import sys

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from arxiv_http import get as arxiv_get, ArxivRateLimitError, cooldown_seconds

ARXIV_ID = re.compile(r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v\d+)?", re.I)
ARXIV_LINK = re.compile(r"https?://(?:www\.)?arxiv\.org/abs/((?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v\d+)?)", re.I)


def normalize_id(value):
    match = ARXIV_ID.fullmatch(value.strip()) if isinstance(value, str) else None
    return re.sub(r"v\d+$", "", match.group(0).lower()) if match else None


def pending_papers(db: Path):
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""SELECT DISTINCT p.arxiv_id, p.title, p.authors, p.summary,
            p.link, p.published_at FROM inbox_items i JOIN papers p ON p.arxiv_id = i.arxiv_id
            WHERE i.status = 'pending' ORDER BY i.created_at DESC LIMIT 20""").fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["summary"] = (row["summary"] or "")[:2000]
        return result


def get_papers(db: Path, ids):
    if not isinstance(ids, list) or not 1 <= len(ids) <= 10:
        raise ValueError("需要 1–10 个 arXiv ID")
    normalized = [normalize_id(value) for value in ids]
    if any(value is None for value in normalized):
        raise ValueError("arXiv ID 无效")
    placeholders = ",".join("?" for _ in normalized)
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT arxiv_id,title,authors,summary,link,published_at FROM papers WHERE lower(arxiv_id) IN (" + placeholders + ")", normalized).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["summary"] = (row["summary"] or "")[:2000]
        return result


def search_arxiv(query, *, sort="relevance", limit=8, start=0, since=None, before=None, order="descending"):
    if sort not in {"relevance", "submittedDate"} or order not in {"ascending", "descending"}:
        raise ValueError("无效的 arXiv 排序")
    if type(limit) is not int or not 1 <= limit <= 100 or type(start) is not int or not 0 <= start <= 30000:
        raise ValueError("arXiv 分页须为每页 1–100 条、偏移 0–30000")
    if not isinstance(query, str) or not query.strip() or len(query) > 160:
        raise ValueError("arXiv 查询长度须为 1–160 字符")
    # Treat the query as a phrase, never as arXiv query syntax.
    phrase = " ".join(query.split())
    if any(c in phrase for c in '"\\') or any(ord(c) < 32 for c in phrase):
        raise ValueError("查询包含不支持的字符")

    def date_bound(value):
        if not isinstance(value, str):
            raise ValueError("arXiv 日期边界须为 ISO 时间")
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("arXiv 日期须包含时区")
        return date.astimezone(timezone.utc)

    lower = date_bound(since) if since is not None else None
    upper = date_bound(before) if before is not None else None
    if lower and upper and lower > upper:
        raise ValueError("arXiv 日期范围无效")
    expression = 'all:"' + phrase + '"'
    if lower or upper:
        first = lower.strftime("%Y%m%d%H%M") if lower else "199101010000"
        last = upper.strftime("%Y%m%d%H%M") if upper else "299912312359"
        expression += " AND submittedDate:[" + first + " TO " + last + "]"
    with arxiv_get("https://export.arxiv.org/api/query", params={
        "search_query": expression, "start": start, "max_results": limit,
        "sortBy": sort, "sortOrder": order},
        timeout=30, stream=True) as response:
        if response.status_code == 429:
            raise ArxivRateLimitError("arXiv 限流，暂时停止在线检索，请稍后重试", cooldown_seconds())
        if response.status_code != 200:
            raise ValueError("arXiv 请求失败")
        chunks = []
        size = 0
        for chunk in response.iter_content(16384):
            size += len(chunk)
            if size > 1_000_000:
                raise ValueError("arXiv 响应过大")
            chunks.append(chunk)
    feed = feedparser.parse(b"".join(chunks))
    if feed.bozo:
        raise ValueError("arXiv 响应无效")
    result = []
    for entry in feed.entries[:limit]:
        raw_id = str(entry.get("id", ""))
        match = ARXIV_LINK.fullmatch(raw_id)
        paper_id = normalize_id(match.group(1)) if match else None
        if not paper_id:
            # A skipped record would make a page appear complete too early.
            raise ValueError("arXiv 响应含无法识别的论文 ID")
        result.append({"arxiv_id": paper_id, "title": str(entry.get("title", ""))[:500],
                       "authors": ", ".join(str(a.get("name", "")) for a in entry.get("authors", [])[:20]),
                       "summary": str(entry.get("summary", ""))[:2000],
                       "link": "https://arxiv.org/abs/" + paper_id,
                       "published_at": str(entry.get("published", ""))[:32]})
    return result


def collect_sources(tool_name, tool_result, sources):
    if tool_name not in {"search_papers", "pending_papers", "get_papers", "search_arxiv", "search_library"}:
        return
    try:
        rows = json.loads(tool_result)
    except (TypeError, ValueError):
        return
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            paper_id = normalize_id(row.get("arxiv_id"))
            if paper_id:
                sources.add(paper_id)


def provenance(answer, sources):
    cited = {normalize_id(match.group(1)) for match in ARXIV_LINK.finditer(answer)}
    unknown = sorted(cited - sources)
    lines = ["\n\n### 来源核对", "以下仅表示本次工具检索到的 arXiv 记录，并非对论文内容或结论的验证。"]
    if sources:
        lines.extend("- https://arxiv.org/abs/" + paper_id for paper_id in sorted(sources))
    else:
        lines.append("本次没有检索到可识别的 arXiv 记录。")
    if unknown:
        lines.append("\n以下回答中的 arXiv 链接未出现在本次检索结果中，请人工核验：")
        lines.extend("- https://arxiv.org/abs/" + paper_id for paper_id in unknown)
    lines.append("其他链接、笔记引用和所有研究结论也需人工核验；检索结果不代表完整文献。")
    return answer + "\n".join(lines)
