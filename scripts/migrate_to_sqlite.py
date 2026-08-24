from __future__ import annotations

import os
from contextlib import closing

from config_loader import get_config_value, load_config
from database import (
    connect_database,
    database_path,
    import_archives,
    import_inbox,
    integrity_check,
    render_inbox,
)


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate() -> None:
    config = load_config(BASE_DIR)
    db_path = database_path(config, BASE_DIR)
    inbox_path = os.path.join(
        BASE_DIR, str(get_config_value(config, "paths.inbox", "Inbox.md"))
    )
    papers_dir = os.path.join(
        BASE_DIR, str(get_config_value(config, "paths.papers_dir", "Papers"))
    )

    with closing(connect_database(db_path)) as connection:
        archived = import_archives(connection, papers_dir)
        inbox = 0
        if os.path.exists(inbox_path):
            with open(inbox_path, "r", encoding="utf-8") as file:
                inbox = import_inbox(connection, file.read())
        rendered = render_inbox(connection, config, inbox_path)
        integrity_check(connection)

    print(
        f"SQLite 迁移完成：归档 {archived} 条，导入 {inbox} 条，"
        f"Inbox 渲染 {rendered} 条，数据库 {db_path}"
    )


if __name__ == "__main__":
    migrate()
