import os
import sys
import tempfile
import unittest
from contextlib import closing


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from database import (  # noqa: E402
    apply_inbox_changes,
    connect_database,
    inbox_changes,
    import_inbox,
    parse_arxiv_id,
    parse_inbox_markdown,
    queue_fetched_papers,
    render_inbox,
    upsert_inbox_item,
    upsert_paper,
)


class DatabaseTests(unittest.TestCase):
    def test_parse_arxiv_id_removes_version(self):
        self.assertEqual(parse_arxiv_id("https://arxiv.org/abs/2608.12345v3"), ("2608.12345", 3))
        self.assertEqual(parse_arxiv_id("cond-mat/0207270v1"), ("cond-mat/0207270", 1))

    def test_import_inbox_preserves_paper_and_version_notice(self):
        markdown = """---

## 2026-08-24 更新 2 篇新论文
- [ ] **[cs.AI]** [Example](https://arxiv.org/abs/2608.12345v1) *by Alice et al. (2026-08-23)* - _Summary_
- [ ] (版本更新) 2026-08-24：2608.99999 从 v1 更新到 v2 - [Update](https://arxiv.org/abs/2608.99999v2)
"""
        items = parse_inbox_markdown(markdown)
        self.assertEqual([item["kind"] for item in items], ["paper", "version_update"])

        with tempfile.TemporaryDirectory() as directory:
            with closing(connect_database(os.path.join(directory, "arxiv.db"))) as connection:
                self.assertEqual(import_inbox(connection, markdown), 2)
                rows = connection.execute(
                    "SELECT item_key, visible FROM inbox_items ORDER BY item_key"
                ).fetchall()
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(row["visible"] == 1 for row in rows))

    def test_archived_item_is_not_reopened(self):
        with tempfile.TemporaryDirectory() as directory:
            with closing(connect_database(os.path.join(directory, "arxiv.db"))) as connection:
                arxiv_id = upsert_paper(
                    connection,
                    {
                        "arxiv_id": "2608.12345",
                        "title": "Example",
                        "link": "https://arxiv.org/abs/2608.12345v1",
                    },
                    "2026-08-24",
                )
                upsert_inbox_item(
                    connection,
                    "paper:2608.12345",
                    arxiv_id,
                    "paper",
                    "2026-08-24",
                    status="archived",
                )
                upsert_inbox_item(
                    connection,
                    "paper:2608.12345",
                    arxiv_id,
                    "paper",
                    "2026-08-25",
                    status="pending",
                )
                status = connection.execute(
                    "SELECT status FROM inbox_items WHERE item_key = 'paper:2608.12345'"
                ).fetchone()[0]
                self.assertEqual(status, "archived")

    def test_queue_and_render_respects_limit(self):
        config = {
            "inbox": {"render": {"max_items": 2, "max_bytes": 10000}},
            "fetch": {"formatting": {}},
        }
        papers = [
            {
                "arxiv_id": f"2608.0000{index}",
                "arxiv_version": 1,
                "category": "cs.AI",
                "title": f"Paper {index}",
                "author": "Author",
                "summary": "Summary",
                "link": f"https://arxiv.org/abs/2608.0000{index}v1",
                "published": "2026-08-24",
            }
            for index in range(3)
        ]

        with tempfile.TemporaryDirectory() as directory:
            inbox_path = os.path.join(directory, "Inbox.md")
            with closing(connect_database(os.path.join(directory, "arxiv.db"))) as connection:
                result = queue_fetched_papers(
                    connection, papers, "append_notice", "2026-08-24T00:00:00+00:00"
                )
                rendered = render_inbox(connection, config, inbox_path)
                visible = connection.execute(
                    "SELECT count(*) FROM inbox_items WHERE visible = 1"
                ).fetchone()[0]

            self.assertEqual(result, {"added": 3, "version_updates": 0})
            self.assertEqual(rendered, 2)
            self.assertEqual(visible, 2)
            with open(inbox_path, "r", encoding="utf-8") as file:
                content = file.read()
            self.assertEqual(content.count("- [ ] **[cs.AI]**"), 2)

    def test_queue_creates_one_version_notice(self):
        original = {
            "arxiv_id": "2608.12345",
            "arxiv_version": 1,
            "title": "Example",
            "link": "https://arxiv.org/abs/2608.12345v1",
        }
        updated = {
            **original,
            "arxiv_version": 2,
            "link": "https://arxiv.org/abs/2608.12345v2",
        }
        with tempfile.TemporaryDirectory() as directory:
            with closing(connect_database(os.path.join(directory, "arxiv.db"))) as connection:
                queue_fetched_papers(connection, [original], "append_notice", "2026-08-23")
                first = queue_fetched_papers(
                    connection, [updated], "append_notice", "2026-08-24"
                )
                second = queue_fetched_papers(
                    connection, [updated], "append_notice", "2026-08-24"
                )
                notices = connection.execute(
                    "SELECT count(*) FROM inbox_items WHERE kind = 'version_update'"
                ).fetchone()[0]

            self.assertEqual(first["version_updates"], 1)
            self.assertEqual(second["version_updates"], 0)
            self.assertEqual(notices, 1)

    def test_inbox_changes_detects_archived_and_dismissed_items(self):
        config = {
            "inbox": {"render": {"max_items": 2, "max_bytes": 10000}},
            "fetch": {"formatting": {}},
        }
        papers = [
            {
                "arxiv_id": f"2608.1000{index}",
                "arxiv_version": 1,
                "category": "cs.AI",
                "title": f"Paper {index}",
                "author": "Author",
                "summary": "Summary",
                "link": f"https://arxiv.org/abs/2608.1000{index}v1",
                "published": "2026-08-24",
            }
            for index in range(2)
        ]
        with tempfile.TemporaryDirectory() as directory:
            inbox_path = os.path.join(directory, "Inbox.md")
            with closing(connect_database(os.path.join(directory, "arxiv.db"))) as connection:
                queue_fetched_papers(connection, papers, seen_at="2026-08-24")
                render_inbox(connection, config, inbox_path)
                with open(inbox_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                entries = [index for index, line in enumerate(lines) if line.startswith("- [ ]")]
                lines[entries[0]] = lines[entries[0]].replace("- [ ]", "- [x]", 1)
                del lines[entries[1]]
                changes = inbox_changes(connection, "".join(lines))
                archived_keys = [row["item_key"] for row in changes["archived"]]
                apply_inbox_changes(connection, archived_keys, changes["dismissed"])
                statuses = dict(
                    connection.execute("SELECT item_key, status FROM inbox_items").fetchall()
                )

            self.assertEqual(len(archived_keys), 1)
            self.assertEqual(len(changes["dismissed"]), 1)
            self.assertEqual(set(statuses.values()), {"archived", "dismissed"})


if __name__ == "__main__":
    unittest.main()
