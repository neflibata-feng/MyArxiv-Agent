"""Independent arXiv subscriptions with bounded, mergeable delivery progress."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
import re
import time

from research_sources import normalize_id, search_arxiv

MAX_TOPICS = 10
MAX_SEEN = 1000
TOPIC_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,39}")


def _topics(config):
    if not isinstance(config, dict) or not isinstance(config.get("agent", {}), dict):
        raise ValueError("agent 配置须为对象")
    raw = config.get("agent", {}).get("subscriptions", [])
    if not isinstance(raw, list) or len(raw) > MAX_TOPICS:
        raise ValueError("论文订阅须为列表，最多 10 个主题")
    result, ids = [], set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("论文订阅项须为对象")
        topic_id, query = entry.get("id"), entry.get("query")
        enabled = entry.get("enabled", True)
        if not isinstance(topic_id, str) or not TOPIC_ID.fullmatch(topic_id) or topic_id in ids:
            raise ValueError("订阅 ID 须唯一，且仅包含字母、数字、下划线和连字符")
        if not isinstance(query, str) or not query.strip() or len(query) > 160:
            raise ValueError("订阅查询长度须为 1–160 字符")
        if any(char in query for char in '\"\\') or any(ord(char) < 32 for char in query):
            raise ValueError("订阅查询包含不支持的字符")
        if type(enabled) is not bool:
            raise ValueError("订阅 enabled 须为布尔值")
        ids.add(topic_id)
        result.append({"id": topic_id, "query": " ".join(query.split()), "enabled": enabled})
    return result


def _history(state):
    if not isinstance(state, dict) or not isinstance(state.get("subscriptions", {}), dict):
        raise ValueError("订阅进度格式无效")
    result = state.get("subscriptions", {})
    for entry in result.values():
        if not isinstance(entry, dict) or not isinstance(entry.get("seen", []), list):
            raise ValueError("订阅进度格式无效")
        if any(not isinstance(value, str) or normalize_id(value) is None or normalize_id(value) != value for value in entry.get("seen", [])):
            raise ValueError("订阅进度包含无效论文 ID")
    return result


def _paper(row):
    if not isinstance(row, dict):
        raise ValueError("论文元数据格式无效")
    paper_id = normalize_id(row.get("arxiv_id"))
    if not paper_id:
        raise ValueError("论文缺少 arXiv ID")
    return {"arxiv_id": paper_id,
            "title": str(row.get("title") or paper_id)[:500],
            "authors": str(row.get("authors") or "")[:2000],
            "summary": str(row.get("summary") or "")[:2000],
            "link": "https://arxiv.org/abs/" + paper_id,
            "published_at": str(row.get("published_at") or "")[:32]}


PAGE_SIZE = 100
MAX_PAGES = 3
ORIGIN = "1991-01-01T00:00:00+00:00"


def _time(value):
    if not isinstance(value, str):
        raise ValueError("订阅时间格式无效")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("订阅时间须包含时区")
    return date.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _cursor(value):
    if not isinstance(value, dict):
        raise ValueError("订阅游标格式无效")
    since, before = _time(value.get("since")), _time(value.get("before"))
    start = value.get("start")
    if since > before or type(start) is not int or start < 0:
        raise ValueError("订阅游标范围无效")
    return {"since": since, "before": before, "start": start}


def collect(config, state, selected_topic="", *, search=None, sleep=None, now=None):
    """Deliver bounded pages from a frozen window; apply updates only after delivery.

    Each topic scans at most three pages per invocation. A frozen submittedDate
    window and ascending order keep new head submissions from moving the offset.
    A completed window advances its checkpoint; the next window overlaps one day
    to accommodate delayed indexing. arXiv may still add older records later, so
    neither this bounded history nor the upstream API guarantees exhaustive recall.
    """
    topics, history = _topics(config), _history(state)
    if not isinstance(selected_topic, str) or (selected_topic and selected_topic not in {t["id"] for t in topics}):
        raise ValueError("找不到指定订阅主题")
    active = [t for t in topics if t["id"] == selected_topic] if selected_topic else [t for t in topics if t["enabled"]]
    search, sleep = search or search_arxiv, sleep or time.sleep
    timestamp = _time(now or datetime.now(timezone.utc).isoformat())
    known = {paper_id for progress in history.values() for paper_id in progress.get("seen", [])}
    current, updates, reports, requests_made = {}, {}, {}, 0
    for topic in active:
        topic_id, previous = topic["id"], history.get(topic["id"], {})
        matching = previous.get("query") == topic["query"]
        if matching and previous.get("cursor"):
            window = _cursor(previous["cursor"])
        else:
            checkpoint = previous.get("checkpoint") if matching else None
            since = (datetime.fromisoformat(_time(checkpoint)) - timedelta(days=1)).isoformat() if checkpoint else ORIGIN
            window = {"since": max(since, ORIGIN), "before": timestamp, "start": 0}
        complete, ok, fetched, pages, new_count = False, True, [], 0, 0
        for _ in range(MAX_PAGES):
            if requests_made:
                sleep(3)
            requests_made += 1
            try:
                raw = search(topic["query"], sort="submittedDate", order="ascending", limit=PAGE_SIZE,
                             start=window["start"], since=window["since"], before=window["before"])
                if not isinstance(raw, list) or len(raw) > PAGE_SIZE:
                    raise ValueError("论文检索响应格式无效")
                papers = [_paper(row) for row in raw]
                for paper in papers:
                    paper_id = paper["arxiv_id"]
                    fetched.append(paper_id)
                    if paper_id in current:
                        if topic_id not in current[paper_id]["subscription_ids"]:
                            current[paper_id]["subscription_ids"].append(topic_id)
                    elif paper_id not in known:
                        current[paper_id] = {**paper, "subscription_ids": [topic_id]}
                        new_count += 1
                window["start"] += len(raw)
                pages += 1
                if len(raw) < PAGE_SIZE:
                    complete = True
                    break
            except Exception:
                # Preserve successfully acquired pages without persisting raw errors.
                ok = False
                break
        error = None if ok else "arXiv 检索失败，可按主题重试；已取得页面可保存并继续"
        updates[topic_id] = {"ok": ok, "query": topic["query"], "seen": list(dict.fromkeys(fetched)),
                             "at": timestamp, "window": window, "complete": complete, "error": error}
        reports[topic_id] = {"ok": ok, "query": topic["query"], "fetched": len(set(fetched)), "new": new_count,
                             "pages": pages, "complete": complete, "backlog": not complete,
                             "next_start": window["start"], "since": window["since"], "before": window["before"],
                             "last_success": timestamp if ok else previous.get("last_success"), "error": error}
    return list(current.values()), updates, {"topics": reports, "new_papers": len(current),
        "successful": sum(r["ok"] for r in reports.values()), "failed": sum(not r["ok"] for r in reports.values()),
        "backlog": sum(r["backlog"] for r in reports.values()), "history_limit": MAX_SEEN,
        "page_size": PAGE_SIZE, "pages_per_topic": MAX_PAGES}


def apply_progress(state, updates):
    """CAS-safe union of delivered IDs and monotonic completed-window checkpoints."""
    merged = deepcopy(_history(state))
    for topic_id, update in updates.items():
        if not TOPIC_ID.fullmatch(topic_id) or not isinstance(update, dict) or type(update.get("ok")) is not bool:
            raise ValueError("订阅更新格式无效")
        previous = deepcopy(merged.get(topic_id, {}))
        timestamp = _time(update.get("at"))
        newest = not previous.get("last_attempt") or timestamp >= _time(previous["last_attempt"])
        seen = update.get("seen", [])
        if not isinstance(seen, list) or any(not isinstance(i, str) or normalize_id(i) is None or normalize_id(i) != i for i in seen):
            raise ValueError("订阅更新包含无效论文 ID")
        older = previous.get("seen", [])
        sequence = older + seen if newest else seen + older
        previous["seen"] = list(reversed(list(dict.fromkeys(reversed(sequence)))))[-MAX_SEEN:]
        same_query = not previous.get("query") or previous.get("query") == update.get("query")
        if not same_query and newest:
            previous.pop("checkpoint", None)
            previous.pop("cursor", None)
            previous.pop("last_success", None)
            same_query = True
        if same_query:
            window = _cursor(update["window"]) if "window" in update else None
            if window:
                checkpoint = previous.get("checkpoint", ORIGIN)
                current = _cursor(previous["cursor"]) if previous.get("cursor") else None
                if update.get("complete"):
                    checkpoint = max(checkpoint, window["before"])
                    previous["checkpoint"] = checkpoint
                    if current and current["before"] <= checkpoint:
                        current = None
                elif window["before"] > checkpoint:
                    if current:
                        # Ascending scans share prefixes for equal lower bounds.
                        # For differing bounds retain the earlier scan conservatively.
                        if current["since"] == window["since"]:
                            current = {"since": current["since"], "before": max(current["before"], window["before"]),
                                       "start": max(current["start"], window["start"])}
                        elif window["since"] < current["since"]:
                            current = window
                    else:
                        current = window
                previous["cursor"] = current
            if update["ok"] and (not previous.get("last_success") or timestamp >= previous["last_success"]):
                previous["last_success"] = timestamp
            if newest:
                previous["query"] = update.get("query", "")
        if newest:
            previous["last_error"] = None if update["ok"] else "arXiv 检索失败，可按主题重试"
            previous["last_attempt"] = timestamp
        merged[topic_id] = previous
    state["subscriptions"] = merged
