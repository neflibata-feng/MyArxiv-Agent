from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import tempfile
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


def queue_fetched_papers(
    connection: sqlite3.Connection,
    papers: Iterable[Dict[str, Any]],
    version_behavior: str = "ignore",
    seen_at: Optional[str] = None,
) -> Dict[str, int]:
    seen = seen_at or utc_now()
    added = 0
    version_updates = 0

    with connection:
        for paper in papers:
            arxiv_id, parsed_version = parse_arxiv_id(
                str(paper.get("arxiv_id") or paper.get("link") or "")
            )
            if not arxiv_id:
                continue
            incoming_version = paper.get("arxiv_version", paper.get("version", parsed_version))
            existing = connection.execute(
                "SELECT version FROM papers WHERE arxiv_id = ?", (arxiv_id,)
            ).fetchone()
            old_version = existing["version"] if existing else None
            arxiv_id = upsert_paper(connection, paper, seen)

            if existing is None:
                upsert_inbox_item(
                    connection, f"paper:{arxiv_id}", arxiv_id, "paper", seen
                )
                added += 1
                continue

            if (
                version_behavior in {"append_notice", "replace"}
                and isinstance(old_version, int)
                and isinstance(incoming_version, int)
                and incoming_version > old_version
            ):
                item_key = f"version:{arxiv_id}:v{incoming_version}"
                existed = connection.execute(
                    "SELECT 1 FROM inbox_items WHERE item_key = ?", (item_key,)
                ).fetchone()
                upsert_inbox_item(
                    connection,
                    item_key,
                    arxiv_id,
                    "version_update",
                    seen,
                    from_version=old_version,
                    to_version=incoming_version,
                )
                if existed is None:
                    version_updates += 1

    return {"added": added, "version_updates": version_updates}


def pending_items(connection: sqlite3.Connection, limit: int) -> List[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            i.item_key, i.kind, i.from_version, i.to_version, i.created_at,
            p.arxiv_id, p.version, p.category, p.title, p.authors, p.summary,
            p.link, p.published_at
        FROM inbox_items AS i
        JOIN papers AS p ON p.arxiv_id = i.arxiv_id
        WHERE i.status = 'pending'
        ORDER BY i.created_at DESC, i.item_key DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()


def _render_item(config: Dict[str, Any], row: sqlite3.Row) -> str:
    if row["kind"] == "version_update":
        template = get_config_value(
            config,
            "fetch.formatting.version_update_notice_template",
            "- [ ] (版本更新) {date}：{arxiv_id} 从 v{old_version} 更新到 v{new_version} - [{title}]({link})",
        )
        return str(template).format(
            date=str(row["created_at"])[:10],
            arxiv_id=row["arxiv_id"],
            old_version=row["from_version"],
            new_version=row["to_version"],
            title=row["title"],
            link=row["link"],
        )

    template = get_config_value(
        config,
        "fetch.formatting.item_template",
        "- [ ] **[{category}]** [{title}]({link}) *by {author} ({published})* - _{summary}_",
    )
    return str(template).format(
        category=row["category"],
        title=row["title"],
        link=row["link"],
        author=row["authors"],
        published=row["published_at"] or "Unknown Date",
        summary=row["summary"],
    )


def _inbox_prefix(path: str, delimiter: str) -> str:
    if not os.path.exists(path):
        return "# 📥 My Arxiv Inbox\n\n这里是你的待阅读区。\n\n---\n"
    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()
    for index, line in enumerate(lines):
        if line.strip() == delimiter:
            return "".join(lines[: index + 1]).rstrip() + "\n"
    return "".join(lines).rstrip() + f"\n\n{delimiter}\n"


def render_inbox(
    connection: sqlite3.Connection,
    config: Dict[str, Any],
    path: str,
) -> int:
    limit = int(get_config_value(config, "inbox.render.max_items", 200))
    max_bytes = int(get_config_value(config, "inbox.render.max_bytes", 900000))
    delimiter = str(
        get_config_value(config, "fetch.formatting.inbox_insert_after_delimiter", "---")
    )
    rows = pending_items(connection, limit)
    prefix = _inbox_prefix(path, delimiter)

    def build(selected: List[sqlite3.Row]) -> str:
        sections: List[str] = [prefix.rstrip(), ""]
        current_date: Optional[str] = None
        group_lines: List[str] = []
        for row in selected:
            item_date = str(row["created_at"])[:10]
            if item_date != current_date:
                if group_lines:
                    sections.extend(group_lines)
                    sections.append("")
                current_date = item_date
                group_lines = []
                count = sum(
                    1
                    for candidate in selected
                    if str(candidate["created_at"])[:10] == item_date
                )
                heading = get_config_value(
                    config,
                    "fetch.formatting.daily_heading_template",
                    "## {date} 更新 {count} 篇新论文",
                )
                sections.append(str(heading).format(date=item_date, count=count))
            group_lines.append(_render_item(config, row))
        if group_lines:
            sections.extend(group_lines)
        return "\n".join(sections).rstrip() + "\n"

    content = build(rows)
    while rows and len(content.encode("utf-8")) > max_bytes:
        rows.pop()
        content = build(rows)

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".inbox-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            file.write(content)
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise

    with connection:
        connection.execute("UPDATE inbox_items SET visible = 0")
        connection.executemany(
            "UPDATE inbox_items SET visible = 1 WHERE item_key = ?",
            [(row["item_key"],) for row in rows],
        )
    return len(rows)
