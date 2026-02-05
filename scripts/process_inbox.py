import os
import re
import datetime
import shutil

# 获取项目根目录 (假设 script 在 scripts/ 目录下)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 配置 (使用绝对路径)
INBOX_FILE = os.path.join(BASE_DIR, "Inbox.md")
PAPERS_DIR = os.path.join(BASE_DIR, "Papers")
NOTES_DIR = os.path.join(BASE_DIR, "Notes")
CONTENTS_FILE = os.path.join(BASE_DIR, "Contents.md")
PDFS_DIR = os.path.join(BASE_DIR, "pdfs")

# 正则匹配 Markdown 中的论文条目
# 格式: - [x] **[Category]** [Title](Link) *by Author (Date)* - _Summary_
# 宽松匹配关键信息
ENTRY_PATTERN = re.compile(
    r'-\s+\[x\]\s+\*\*\[(.*?)\]\*\*\s+\[(.*?)\]\((.*?)\).*'
)

def ensure_dirs():
    for d in [PAPERS_DIR, NOTES_DIR, PDFS_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

def sanitize_filename(name):
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def create_note_template(category, title, link, date_str):
    """
    创建一个 Markdown 笔记模板
    """
    safe_title = sanitize_filename(title)
    # 按分类建立子文件夹
    note_dir = os.path.join(NOTES_DIR, sanitize_filename(category))
    if not os.path.exists(note_dir):
        os.makedirs(note_dir)
        
    note_path = os.path.join(note_dir, f"{safe_title}.md")
    
    # 如果笔记已存在，跳过创建（防止覆盖笔记）
    if os.path.exists(note_path):
        return note_path
        
    content = f"""# {title}

- **Category**: {category}
- **Link**: {link}
- **Date**: {date_str}

## 1. 摘要


## 2. 关键成果
- 

## 3. 核心技术
- 

## 4. 实验及其结果
- 

## 5. 我的观点
- 
"""
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    return note_path

def append_to_papers_archive(category, title, link, date_str):
    """
    将元数据追加到 Papers/Category.md 中
    """
    safe_cat = sanitize_filename(category)
    # 为了方便索引，不仅放在 Papers/Dir 下，还维护一个 Papers/List.md
    
    cat_dir = os.path.join(PAPERS_DIR, safe_cat)
    if not os.path.exists(cat_dir):
        os.makedirs(cat_dir)
        
    archive_file = os.path.join(cat_dir, "List.md")
    
    entry_line = f"- [{title}]({link}) - *{date_str}* [Notes](../../Notes/{safe_cat}/{sanitize_filename(title)}.md)\n"
    
    if not os.path.exists(archive_file):
        with open(archive_file, "w", encoding="utf-8") as f:
            f.write(f"# {category} 论文已处理\n\n")
    
    with open(archive_file, "a", encoding="utf-8") as f:
        f.write(entry_line)

def update_contents_index():
    """
    全量扫描 Papers/ 目录，重新生成 Contents.md
    """
    print("Regenerating Contents.md...")
    
    lines = ["# 🗂️ Contents Index\n\n"]
    lines.append(f"> 上次更新时间为 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    
    # 遍历 Papers 目录下的子文件夹
    for cat_name in sorted(os.listdir(PAPERS_DIR)):
        cat_path = os.path.join(PAPERS_DIR, cat_name)
        if not os.path.isdir(cat_path):
            continue
            
        list_file = os.path.join(cat_path, "List.md")
        if not os.path.exists(list_file):
            continue
        
        lines.append(f"## {cat_name}\n\n")
        
        # 读取该分类 List.md 中的所有条目（排除标题行）
        with open(list_file, "r", encoding="utf-8") as f:
            cat_lines = f.readlines()
            for cl in cat_lines:
                if cl.strip().startswith("-"):
                    fixed_line = cl.replace("../../Notes", "Notes")
                    lines.append(fixed_line)
        lines.append("\n")

    with open(CONTENTS_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

def process_inbox():
    if not os.path.exists(INBOX_FILE):
        print("未找到文本")
        return

    ensure_dirs()
    
    with open(INBOX_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_inbox_lines = []
    archived_count = 0
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    for line in lines:
        # 检查是否是被选中的行 ([x])
        match = ENTRY_PATTERN.search(line)
        if match:
            # 提取元数据
            category = match.group(1).strip()
            title = match.group(2).strip()
            link = match.group(3).strip()
            
            print(f"提取 [{category}] {title}")
            
            # 1. 归档到 Papers/Category/List.md
            append_to_papers_archive(category, title, link, today_str)
            
            # 2. 创建笔记模板 Notes/Category/Title.md
            create_note_template(category, title, link, today_str)
            
            # 3. (可选) 下载 PDF
            
            archived_count += 1
            # 这一行不再写入 new_inbox_lines，相当于从 Inbox 删除了
        else:
            # 未选中的行，或者普通文本行，保留
            new_inbox_lines.append(line)
    
    if archived_count > 0:
        # 写回 Inbox.md (相当于删除了已归档的行)
        with open(INBOX_FILE, "w", encoding="utf-8") as f:
            f.writelines(new_inbox_lines)
        
        # 更新总索引
        update_contents_index()
        print(f"成功处理 {archived_count} 篇论文")
    else:
        print("没有论文被标记需归档")

if __name__ == "__main__":
    process_inbox()
