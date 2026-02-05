import datetime
import urllib.parse
import feedparser
import os

# 配置：需要关注的 arXiv 分类
CATEGORIES = ["cs.AI"]
# 关键词过滤 (标题或摘要中必须包含)
KEYWORDS = ["Agent"]

# 获取项目根目录 (假设 script 在 scripts/ 目录下)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def fetch_papers():
    """
    爬取 arXiv 数据
    """
    print(f"获取日期为 {datetime.date.today()}...")
    
    base_url = 'http://export.arxiv.org/api/query?'
    
    # 构建查询
    cat_query = ' OR '.join([f'cat:{c}' for c in CATEGORIES])
    kw_query = ' OR '.join([f'all:{k}' for k in KEYWORDS])
    
    search_query = f'({cat_query}) AND ({kw_query})'
    
    params = {
        'search_query': search_query,
        'start': 0,
        'max_results': 150,  # 增加到 150 以确保不遗漏
        'sortBy': 'submittedDate',
        'sortOrder': 'descending'
    }
    
    query_string = urllib.parse.urlencode(params)
    url = base_url + query_string
    print(f"查询链接为: {url}")
    
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"获取数据错误: {e}")
        return []

    papers = []
    for entry in feed.entries:
        try:
            # 提取信息
            title = entry.title.replace('\n', ' ').strip()
            link = entry.link
            
            # primary_category
            if hasattr(entry, 'arxiv_primary_category'):
                category = entry.arxiv_primary_category['term']
            else:
                category = 'Unknown'
            
            # Authors
            authors = [a.name for a in entry.authors]
            if len(authors) > 1:
                author_str = f"{authors[0]} et al."
            elif len(authors) == 1:
                author_str = authors[0]
            else:
                author_str = "Unknown"

            # Published Date
            if hasattr(entry, 'published_parsed'):
                pub_date = datetime.date(*entry.published_parsed[:3]).strftime("%Y-%m-%d")
            else:
                pub_date = "Unknown Date"
            
            # Summary
            summary = entry.summary.replace('\n', ' ').strip()
            # 简单清理 LaTeX 标记
            summary_hint = summary[:250] + "..." if len(summary) > 250 else summary
            
            papers.append({
                'title': title,
                'link': link,
                'category': category,
                'summary': summary_hint,
                'published': pub_date,
                'author': author_str
            })
        except Exception as e:
            print(f"Skipping entry due to error: {e}")
            continue
            
    return papers

def update_inbox(papers):
    """
    将新论文追加到 Inbox.md 头部 (带去重功能)
    """
    if not papers:
        print("没有论文更新")
        return

    file_path = os.path.join(BASE_DIR, "Inbox.md")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    # --- 去重逻辑 ---
    existing_links = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            for p in papers:
                if p['link'] in content:
                    existing_links.add(p['link'])
    
    new_papers = [p for p in papers if p['link'] not in existing_links]
    
    if not new_papers:
        print("没有论文更新")
        return

    print(f"获取到 {len(papers)} 篇论文. 其中{len(new_papers)} 篇是新的")
    # ----------------
    
    new_lines = []
    new_lines.append(f"## {today_str} 更新 {len(new_papers)} 篇新论文\n")
    for p in new_papers:
        # Markdown 格式优化
        line = f"- [ ] **[{p['category']}]** [{p['title']}]({p['link']}) *by {p['author']} ({p['published']})* - _{p['summary']}_\n"
        new_lines.append(line)
    new_lines.append("\n")

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    else:
        old_lines = ["# 📥 My Arxiv Inbox\n\n", "这里是你的待阅读区。\n\n", "---\n\n"]

    insert_index = -1
    for i, line in enumerate(old_lines):
        if line.strip() == "---":
            insert_index = i + 1
            break
    
    if insert_index == -1:
        old_lines.append("\n---\n")
        insert_index = len(old_lines)

    final_lines = old_lines[:insert_index] + ["\n"] + new_lines + old_lines[insert_index:]

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(final_lines)
    
    print(f"成功添加 {len(new_papers)} 篇论文至 {file_path}")

if __name__ == "__main__":
    papers = fetch_papers()
    update_inbox(papers)
