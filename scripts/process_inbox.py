import os
import re
import datetime
import shutil

from typing import Pattern

from config_loader import load_config, get_config_value

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text or "")


def _sanitize_filename(config, name: str) -> str:
    strip_ctrl = bool(get_config_value(config, "safety.strip_control_chars", True))
    sanitize = bool(get_config_value(config, "safety.sanitize_filenames", True))

    value = str(name or "")
    if strip_ctrl:
        value = _strip_control_chars(value)

    # Always prevent path traversal / separator issues.
    value = value.replace("/", "_").replace("\\", "_")

    if not sanitize:
        return value.strip()

    return re.sub(r'[\\/*?:"<>|]', "", value).strip()


def _paths_from_config(config):
    inbox_rel = get_config_value(config, "paths.inbox", "Inbox.md")
    papers_rel = get_config_value(config, "paths.papers_dir", "Papers")
    notes_rel = get_config_value(config, "paths.notes_dir", "Notes")
    contents_rel = get_config_value(config, "paths.contents", "Contents.md")
    pdfs_rel = get_config_value(config, "paths.pdfs_dir", "pdfs")

    return {
        "inbox": os.path.join(BASE_DIR, inbox_rel),
        "papers": os.path.join(BASE_DIR, papers_rel),
        "notes": os.path.join(BASE_DIR, notes_rel),
        "contents": os.path.join(BASE_DIR, contents_rel),
        "pdfs": os.path.join(BASE_DIR, pdfs_rel),
    }


def _entry_pattern_from_config(config) -> Pattern:
    checked = str(get_config_value(config, "archive.checkbox.checked", "x"))
    default_pattern = rf"-\s+\[{re.escape(checked)}\]\s+\*\*\[(.*?)\]\*\*\s+\[(.*?)\]\((.*?)\).*"
    pattern = str(
        get_config_value(
            config,
            "archive.parsing.entry_regex",
            default_pattern,
        )
    )

    if checked != "x" and "\\[x\\]" in pattern and f"\\[{checked}\\]" not in pattern:
        pattern = pattern.replace("\\[x\\]", rf"\\[{re.escape(checked)}\\]")

    return re.compile(pattern)

def ensure_dirs(papers_dir: str, notes_dir: str, pdfs_dir: str):
    for d in [papers_dir, notes_dir, pdfs_dir]:
        if not os.path.exists(d):
            os.makedirs(d)

def create_note_template(config, notes_dir: str, category, title, link, date_str):
    safe_title = _sanitize_filename(config, title)
    note_dir = os.path.join(notes_dir, _sanitize_filename(config, category))
    if not os.path.exists(note_dir):
        os.makedirs(note_dir)
        
    note_path = os.path.join(note_dir, f"{safe_title}.md")
    
    if os.path.exists(note_path):
        return note_path
        
    sections = get_config_value(
        config,
        "archive.notes.template.sections",
        [
            "## 1. 摘要",
            "## 2. 关键成果",
            "## 3. 核心技术",
            "## 4. 实验及其结果",
            "## 5. 我的观点",
        ],
    )

    title_prefix = get_config_value(config, "archive.notes.template.title_prefix", "# ")
    title_line = f"{title_prefix}{title}" if str(title_prefix) else str(title)

    content_lines = [
        title_line,
        "",
        f"- **Category**: {category}",
        f"- **Link**: {link}",
        f"- **Date**: {date_str}",
        "",
    ]
    for s in sections:
        content_lines.append(str(s))
        content_lines.append("")
        content_lines.append("")

    content = "\n".join(content_lines)
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return note_path

def append_to_papers_archive(config, papers_dir: str, category, title, link, date_str):
    safe_cat = _sanitize_filename(config, category)
    
    cat_dir = os.path.join(papers_dir, safe_cat)
    if not os.path.exists(cat_dir):
        os.makedirs(cat_dir)
        
    archive_file = os.path.join(cat_dir, "List.md")
    
    notes_rel_tpl = get_config_value(
        config,
        "archive.links.notes_rel_path_template",
        "../../Notes/{category}/{title}.md",
    )
    notes_rel_path = notes_rel_tpl.format(
        category=safe_cat,
        title=f"{_sanitize_filename(config, title)}",
    )

    entry_tpl = get_config_value(
        config,
        "archive.papers.list_entry_template",
        "- [{title}]({link}) - *{date}* [Notes]({notes_rel_path})",
    )
    entry_line = (
        entry_tpl.format(
            title=title,
            link=link,
            date=date_str,
            notes_rel_path=notes_rel_path,
        )
        + "\n"
    )
    
    if not os.path.exists(archive_file):
        with open(archive_file, "w", encoding="utf-8") as f:
            f.write(f"# {category} 论文已处理\n\n")
    
    with open(archive_file, "a", encoding="utf-8") as f:
        f.write(entry_line)

def update_contents_index(config, papers_dir: str, contents_file: str):
    print("Regenerating Contents.md...")

    title = get_config_value(config, "archive.contents.title", "# 🗂️ Contents Index")
    updated_prefix = get_config_value(config, "archive.contents.updated_prefix", "> 上次更新时间为 ")
    updated_time_format = get_config_value(
        config, "archive.contents.updated_time_format", "%Y-%m-%d %H:%M"
    )

    lines = [str(title) + "\n\n"]
    lines.append(
        f"{updated_prefix}{datetime.datetime.now().strftime(str(updated_time_format))}\n\n"
    )
    
    for cat_name in sorted(os.listdir(papers_dir)):
        cat_path = os.path.join(papers_dir, cat_name)
        if not os.path.isdir(cat_path):
            continue
            
        list_file = os.path.join(cat_path, "List.md")
        if not os.path.exists(list_file):
            continue
        
        lines.append(f"## {cat_name}\n\n")
        
        with open(list_file, "r", encoding="utf-8") as f:
            cat_lines = f.readlines()
            for cl in cat_lines:
                if cl.strip().startswith("-"):
                    fixed_line = cl.replace("../../Notes", "Notes")
                    lines.append(fixed_line)
        lines.append("\n")

    with open(contents_file, "w", encoding="utf-8") as f:
        f.writelines(lines)

def process_inbox():
    config = load_config(BASE_DIR)
    paths = _paths_from_config(config)

    inbox_file = paths["inbox"]
    papers_dir = paths["papers"]
    notes_dir = paths["notes"]
    contents_file = paths["contents"]
    pdfs_dir = paths["pdfs"]

    entry_pattern = _entry_pattern_from_config(config)

    if not os.path.exists(inbox_file):
        print("未找到文本")
        return

    ensure_dirs(papers_dir, notes_dir, pdfs_dir)
    
    with open(inbox_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_inbox_lines = []
    archived_count = 0
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    for line in lines:
        match = entry_pattern.search(line)
        if match:
            category = match.group(1).strip()
            title = match.group(2).strip()
            link = match.group(3).strip()
            
            print(f"提取 [{category}] {title}")
            
            append_to_papers_archive(config, papers_dir, category, title, link, today_str)
            
            create_note_template(config, notes_dir, category, title, link, today_str)
            
            archived_count += 1
        else:
            new_inbox_lines.append(line)
    
    if archived_count > 0:
        with open(inbox_file, "w", encoding="utf-8") as f:
            f.writelines(new_inbox_lines)
        
        update_contents_index(config, papers_dir, contents_file)
        print(f"成功处理 {archived_count} 篇论文")
    else:
        print("没有论文被标记需归档")

if __name__ == "__main__":
    process_inbox()
