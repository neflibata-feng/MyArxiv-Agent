from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from config_loader import get_config_value


ARXIV_URL_RE = re.compile(r"https?://arxiv\.org/abs/([^\s)\]]+)", re.IGNORECASE)
VERSION_RE = re.compile(r"^(?P<base>.+?)(?:v(?P<version>\d+))?$", re.IGNORECASE)
NORMAL_ENTRY_RE = re.compile(
    r"^- \[(?P<checked>[xX ])\]\s+\*\*\[(?P<category>.*?)\]\*\*\s+"
    r"\[(?P<title>.*?)\]\((?P<link>https?://arxiv\.org/abs/[^\s)]+)\)"
    r"\s+\*by (?P<authors>.*?) \((?P<published>.*?)\)\*\s+-\s+_(?P<summary>.*)_\s*$"
)
VERSION_ENTRY_RE = re.compile(
    r"^- \[(?P<checked>[xX ])\]\s+\(版本更新\)\s+(?P<date>\d{4}-\d{2}-\d{2})："
    r"(?P<base>\S+)\s+从 v(?P<from_version>\d+) 更新到 v(?P<to_version>\d+)\s+-\s+"
    r"\[(?P<title>.*?)\]\((?P<link>https?://arxiv\.org/abs/[^\s)]+)\)\s*$"
)
ARCHIVE_ENTRY_RE = re.compile(
    r"^- \[(?P<title>.*?)\]\((?P<link>https?://arxiv\.org/abs/[^\s)]+)\)\s+-\s+"
    r"\*(?P<date>[^*]+)\*"
)
HEADING_DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_arxiv_id(value: str) -> tuple[Optional[str], Optional[int]]:
    raw = str(value or "").strip()
    url_match = ARXIV_URL_RE.search(raw)
    if url_match:
        raw = url_match.group(1)
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    if not raw:
        return None, None
    match = VERSION_RE.match(raw)
    if not match:
        return raw, None
    version = match.group("version")
    return match.group("base"), int(version) if version else None


def database_path(config: Dict[str, Any], base_dir: str) -> str:
    relative = str(get_config_value(config, "storage.sqlite.path", "data/arxiv.db"))
    root = Path(base_dir).resolve()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise ValueError("storage.sqlite.path 必须位于项目目录内")
    return str(path)


def connect_database(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = DELETE")
    initialize_database(connection)
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS papers (
            arxiv_id TEXT PRIMARY KEY,
            version INTEGER,
            category TEXT NOT NULL DEFAULT 'Unknown',
            title TEXT NOT NULL,
            authors TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL,
            published_at TEXT,
            updated_at TEXT,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            raw_data TEXT
        );

        CREATE TABLE IF NOT EXISTS inbox_items (
            item_key TEXT PRIMARY KEY,
            arxiv_id TEXT NOT NULL REFERENCES papers(arxiv_id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('paper', 'version_update')),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'archived', 'dismissed')),
            from_version INTEGER,
            to_version INTEGER,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            visible INTEGER NOT NULL DEFAULT 0 CHECK (visible IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_inbox_queue
        ON inbox_items(status, created_at DESC, item_key);

        CREATE INDEX IF NOT EXISTS idx_inbox_visible
        ON inbox_items(visible, status);
        """
    )
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    connection.commit()


def upsert_paper(
    connection: sqlite3.Connection,
    paper: Dict[str, Any],
    seen_at: Optional[str] = None,
) -> str:
    arxiv_id, parsed_version = parse_arxiv_id(
        str(paper.get("arxiv_id") or paper.get("link") or "")
    )
    if not arxiv_id:
        raise ValueError("论文缺少有效的 arXiv ID")

    seen = seen_at or utc_now()
    version = paper.get("arxiv_version", paper.get("version", parsed_version))
    link = str(paper.get("link") or f"https://arxiv.org/abs/{arxiv_id}")
    raw_data = paper.get("raw_data")
    if raw_data is not None and not isinstance(raw_data, str):
        raw_data = json.dumps(raw_data, ensure_ascii=False, sort_keys=True)

    connection.execute(
        """
        INSERT INTO papers(
            arxiv_id, version, category, title, authors, summary, link,
            published_at, updated_at, first_seen_at, last_seen_at, raw_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(arxiv_id) DO UPDATE SET
            version = CASE
                WHEN excluded.version IS NULL THEN papers.version
                WHEN papers.version IS NULL OR excluded.version >= papers.version THEN excluded.version
                ELSE papers.version
            END,
            category = CASE WHEN excluded.category = '' THEN papers.category ELSE excluded.category END,
            title = CASE WHEN excluded.title = '' THEN papers.title ELSE excluded.title END,
            authors = CASE WHEN excluded.authors = '' THEN papers.authors ELSE excluded.authors END,
            summary = CASE WHEN excluded.summary = '' THEN papers.summary ELSE excluded.summary END,
            link = CASE
                WHEN excluded.version IS NULL OR papers.version IS NULL OR excluded.version >= papers.version
                THEN excluded.link ELSE papers.link
            END,
            published_at = COALESCE(excluded.published_at, papers.published_at),
            updated_at = COALESCE(excluded.updated_at, papers.updated_at),
            last_seen_at = excluded.last_seen_at,
            raw_data = COALESCE(excluded.raw_data, papers.raw_data)
        """,
        (
            arxiv_id,
            version,
            str(paper.get("category") or "Unknown"),
            str(paper.get("title") or arxiv_id),
            str(paper.get("authors") or paper.get("author") or ""),
            str(paper.get("summary") or ""),
            link,
            paper.get("published_at", paper.get("published")),
            paper.get("updated_at", paper.get("updated")),
            seen,
            seen,
            raw_data,
        ),
    )
    return arxiv_id


def upsert_inbox_item(
    connection: sqlite3.Connection,
    item_key: str,
    arxiv_id: str,
    kind: str,
    created_at: str,
    status: str = "pending",
    from_version: Optional[int] = None,
    to_version: Optional[int] = None,
    visible: bool = False,
) -> None:
    processed_at = created_at if status != "pending" else None
    connection.execute(
        """
        INSERT INTO inbox_items(
            item_key, arxiv_id, kind, status, from_version, to_version,
            created_at, processed_at, visible
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_key) DO UPDATE SET
            status = CASE
                WHEN inbox_items.status = 'archived' THEN inbox_items.status
                ELSE excluded.status
            END,
            from_version = COALESCE(excluded.from_version, inbox_items.from_version),
            to_version = COALESCE(excluded.to_version, inbox_items.to_version),
            processed_at = COALESCE(excluded.processed_at, inbox_items.processed_at),
            visible = MAX(inbox_items.visible, excluded.visible)
        """,
        (
            item_key,
            arxiv_id,
            kind,
            status,
            from_version,
            to_version,
            created_at,
            processed_at,
            1 if visible else 0,
        ),
    )


def parse_inbox_markdown(content: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    heading_date: Optional[str] = None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        heading = HEADING_DATE_RE.match(line)
        if heading:
            heading_date = heading.group(1)
            continue

        normal = NORMAL_ENTRY_RE.match(line)
        if normal:
            values = normal.groupdict()
            arxiv_id, version = parse_arxiv_id(values["link"])
            if not arxiv_id:
                continue
            items.append(
                {
                    "item_key": f"paper:{arxiv_id}",
                    "kind": "paper",
                    "checked": values["checked"].lower() == "x",
                    "created_at": heading_date or values["published"] or utc_now(),
                    "paper": {
                        "arxiv_id": arxiv_id,
                        "arxiv_version": version,
                        "category": values["category"],
                        "title": values["title"],
                        "authors": values["authors"],
                        "summary": values["summary"],
                        "link": values["link"],
                        "published": values["published"],
                    },
                }
            )
            continue

        notice = VERSION_ENTRY_RE.match(line)
        if notice:
            values = notice.groupdict()
            arxiv_id, version = parse_arxiv_id(values["link"])
            if not arxiv_id:
                continue
            to_version = int(values["to_version"])
            items.append(
                {
                    "item_key": f"version:{arxiv_id}:v{to_version}",
                    "kind": "version_update",
                    "checked": values["checked"].lower() == "x",
                    "created_at": heading_date or values["date"],
                    "from_version": int(values["from_version"]),
                    "to_version": to_version,
                    "paper": {
                        "arxiv_id": arxiv_id,
                        "arxiv_version": version or to_version,
                        "title": values["title"],
                        "link": values["link"],
                    },
                }
            )
    return items


def import_inbox(connection: sqlite3.Connection, content: str) -> int:
    items = parse_inbox_markdown(content)
    with connection:
        connection.execute("UPDATE inbox_items SET visible = 0")
        for item in items:
            arxiv_id = upsert_paper(connection, item["paper"], item["created_at"])
            upsert_inbox_item(
                connection,
                item["item_key"],
                arxiv_id,
                item["kind"],
                item["created_at"],
                status="archived" if item["checked"] else "pending",
                from_version=item.get("from_version"),
                to_version=item.get("to_version"),
                visible=True,
            )
    return len(items)


def import_archives(connection: sqlite3.Connection, papers_dir: str) -> int:
    imported = 0
    root = Path(papers_dir)
    if not root.exists():
        return imported

    with connection:
        for list_path in root.rglob("List.md"):
            category = list_path.parent.name
            for raw_line in list_path.read_text(encoding="utf-8").splitlines():
                match = ARCHIVE_ENTRY_RE.match(raw_line.strip())
                if not match:
                    continue
                values = match.groupdict()
                arxiv_id, version = parse_arxiv_id(values["link"])
                if not arxiv_id:
                    continue
                arxiv_id = upsert_paper(
                    connection,
                    {
                        "arxiv_id": arxiv_id,
                        "arxiv_version": version,
                        "category": category,
                        "title": values["title"],
                        "link": values["link"],
                        "published": values["date"].strip(),
                    },
                    values["date"].strip(),
                )
                upsert_inbox_item(
                    connection,
                    f"paper:{arxiv_id}",
                    arxiv_id,
                    "paper",
                    values["date"].strip(),
                    status="archived",
                )
                imported += 1
    return imported


def integrity_check(connection: sqlite3.Connection) -> None:
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"SQLite integrity_check 失败: {result}")
