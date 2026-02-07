import datetime
import urllib.parse
import feedparser
import os
import re
import time

import requests

from typing import Optional, Any, Dict, List

from config_loader import load_config, get_config_value

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_ARXIV_ABS_RE = re.compile(r"arxiv\.org/abs/([^\s\)\]]+)", re.IGNORECASE)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def _read_text_if_exists(path: str) -> str:
    try:
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read() or ""
    except Exception:
        return ""
    return ""


def _scan_arxiv_versions_from_text(content: str):
    """Scan markdown text and return (links_set, versions_by_base_id)."""
    links = set()
    versions = {}
    if not content:
        return links, versions

    for match in _ARXIV_ABS_RE.finditer(content):
        raw = match.group(1)
        base, ver = _parse_arxiv_id_and_version(raw)
        if base:
            old = versions.get(base)
            if ver is None:
                if old is None:
                    versions[base] = None
            else:
                if old is None or (isinstance(old, int) and ver > old):
                    versions[base] = ver
            # store the matched link (best-effort)
            links.add(f"https://arxiv.org/abs/{raw}")

    # Also capture any http links in markdown parentheses (for link-based dedupe)
    for m in re.finditer(r"\((https?://[^\)]+)\)", content):
        links.add(m.group(1))

    return links, versions


def _scan_archived_index(config):
    """Build a dedupe index from already-archived metadata.

    When a paper is archived, it is appended into Papers/*/List.md and mirrored
    into Contents.md. If we only dedupe against Inbox.md, archived papers can be
    re-added on the next fetch.
    """

    contents_rel = get_config_value(config, "paths.contents", "Contents.md")
    papers_rel = get_config_value(config, "paths.papers_dir", "Papers")

    contents_path = os.path.join(BASE_DIR, contents_rel)
    papers_dir = os.path.join(BASE_DIR, papers_rel)

    archived_links = set()
    archived_versions_by_id = {}

    # 1) Scan Contents.md (fast path)
    content = _read_text_if_exists(contents_path)
    links, versions = _scan_arxiv_versions_from_text(content)
    archived_links |= links
    archived_versions_by_id.update(versions)

    # 2) Scan Papers/**/List.md (fallback / redundancy)
    try:
        if os.path.isdir(papers_dir):
            for root, _dirs, files in os.walk(papers_dir):
                for fn in files:
                    if fn.lower() != "list.md":
                        continue
                    p = os.path.join(root, fn)
                    t = _read_text_if_exists(p)
                    l2, v2 = _scan_arxiv_versions_from_text(t)
                    archived_links |= l2
                    for k, v in v2.items():
                        old = archived_versions_by_id.get(k)
                        if old is None:
                            archived_versions_by_id[k] = v
                        elif isinstance(old, int) and isinstance(v, int) and v > old:
                            archived_versions_by_id[k] = v
    except Exception:
        pass

    return archived_links, archived_versions_by_id


def _strip_control_chars(text: str) -> str:
    return _CONTROL_CHARS_RE.sub("", text or "")


def _maybe_clean_text(config, text: str) -> str:
    if bool(get_config_value(config, "safety.strip_control_chars", True)):
        return _strip_control_chars(text)
    return text


def _parse_arxiv_id_and_version(arxiv_id_with_optional_version: str):
    raw = (arxiv_id_with_optional_version or "").strip()
    if not raw:
        return None, None

    raw = raw.split("?")[0].split("#")[0]

    m = re.match(r"^(?P<base>.+?)(?:v(?P<ver>\d+))?$", raw, re.IGNORECASE)
    if not m:
        return raw, None

    base = m.group("base")
    ver = m.group("ver")
    try:
        version = int(ver) if ver is not None else None
    except Exception:
        version = None
    return base, version


def _extract_abs_link(entry) -> Optional[str]:
    try:
        for l in getattr(entry, "links", []) or []:
            if getattr(l, "rel", None) == "alternate" and getattr(l, "href", None):
                return str(l.href)
    except Exception:
        pass
    return str(getattr(entry, "link", "") or "") or None


def _extract_arxiv_id_from_url(url: str):
    if not url:
        return None, None
    m = _ARXIV_ABS_RE.search(url)
    if not m:
        return None, None
    return _parse_arxiv_id_and_version(m.group(1))


def _normalize_id_list(value: Any) -> List[str]:
    """Normalize config `fetch.query.id_list` into a list of arXiv ids.

    Supports:
    - [] / list
    - comma-separated string

    Items may include versions (e.g. "cond-mat/0207270v1").
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return [p for p in parts if p]
    s = str(value).strip()
    return [s] if s else []


def _scan_existing_inbox_for_arxiv_versions(content: str):
    versions = {}
    if not content:
        return versions

    for match in _ARXIV_ABS_RE.finditer(content):
        base, ver = _parse_arxiv_id_and_version(match.group(1))
        if not base:
            continue
        old = versions.get(base)
        if ver is None:
            if old is None:
                versions[base] = None
            continue
        if old is None or (isinstance(old, int) and ver > old):
            versions[base] = ver
    return versions

def fetch_papers():
    config = load_config(BASE_DIR)

    print(f"获取日期为 {datetime.date.today()}...")

    base_url = get_config_value(
        config,
        "fetch.arxiv_api.base_url",
        "https://export.arxiv.org/api/query",
    )

    sort_by = get_config_value(config, "fetch.arxiv_api.sort_by", "submittedDate")
    sort_order = get_config_value(config, "fetch.arxiv_api.sort_order", "descending")
    start = get_config_value(config, "fetch.arxiv_api.start", 0)
    max_results = get_config_value(config, "fetch.arxiv_api.max_results", 150)

    try:
        start = int(start)
    except Exception:
        raise ValueError("fetch.arxiv_api.start 必须是 >= 0 的整数")
    if start < 0:
        raise ValueError("fetch.arxiv_api.start 必须是 >= 0 的整数（arXiv API 为 0-based）")

    try:
        max_results = int(max_results)
    except Exception:
        max_results = 150

    if max_results > 2000:
        print("max_results 超过 2000，将自动限制为 2000（arXiv API 限制）")
        max_results = 2000
    if max_results <= 0:
        max_results = 1

    timeout_seconds = get_config_value(config, "fetch.arxiv_api.http.timeout_seconds", 30)
    retries = get_config_value(config, "fetch.arxiv_api.http.retries", 3)
    backoff_seconds = get_config_value(config, "fetch.arxiv_api.http.backoff_seconds", 2)
    min_delay_seconds = get_config_value(config, "fetch.arxiv_api.http.min_delay_seconds", 3)
    user_agent = get_config_value(
        config,
        "fetch.arxiv_api.http.user_agent",
        "MyArxiv-Agent/1.0 (+https://github.com/)",
    )

    categories = get_config_value(config, "fetch.query.categories", ["cs.AI"])
    keywords = get_config_value(config, "fetch.query.keywords", ["Agent"])
    keyword_field = get_config_value(config, "fetch.query.keyword_field", "all")
    combine_mode = get_config_value(config, "fetch.query.combine_mode", "(cat_or) AND (kw_or)")
    id_list = _normalize_id_list(get_config_value(config, "fetch.query.id_list", []))
    
    cat_query = " OR ".join([f"cat:{c}" for c in categories]) if categories else ""
    kw_query = " OR ".join([f"{keyword_field}:{k}" for k in keywords]) if keywords else ""

    if cat_query and kw_query:
        search_query = str(combine_mode).replace("cat_or", cat_query).replace("kw_or", kw_query)
    elif cat_query:
        search_query = cat_query
    elif kw_query:
        search_query = kw_query
    else:
        search_query = "" if id_list else "all:agent"
    
    params = {
        'start': start,
        'max_results': max_results,
        'sortBy': sort_by,
        'sortOrder': sort_order,
    }
    if search_query:
        params['search_query'] = search_query
    if id_list:
        params['id_list'] = ",".join(id_list)

    query_string = urllib.parse.urlencode(params)
    url_for_print = f"{base_url}?{query_string}"
    print(f"查询链接为: {url_for_print}")

    last_error: Optional[Exception] = None
    last_request_ts: Optional[float] = None
    for attempt in range(int(retries) + 1):
        try:
            if last_request_ts is not None:
                elapsed = time.time() - last_request_ts
                try:
                    min_delay = float(min_delay_seconds)
                except Exception:
                    min_delay = 3.0
                if elapsed < min_delay:
                    time.sleep(min_delay - elapsed)

            resp = requests.get(
                base_url,
                params=params,
                timeout=float(timeout_seconds),
                headers={"User-Agent": str(user_agent)},
            )
            last_request_ts = time.time()
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)
            last_error = None
            break
        except Exception as e:
            last_error = e
            if attempt >= int(retries):
                break
            sleep_seconds = float(backoff_seconds) * (2**attempt)
            try:
                min_delay = float(min_delay_seconds)
            except Exception:
                min_delay = 3.0
            sleep_seconds = max(sleep_seconds, min_delay)
            print(f"获取数据错误(第{attempt+1}次): {e}; {sleep_seconds:.1f}s 后重试...")
            time.sleep(sleep_seconds)

    if last_error is not None:
        print(f"获取数据错误: {last_error}")
        return []

    papers = []
    for entry in feed.entries:
        try:
            title = _maybe_clean_text(config, entry.title).replace('\n', ' ').strip()
            link = _extract_abs_link(entry) or ""
            arxiv_id, arxiv_version = _extract_arxiv_id_from_url(link)
            
            if hasattr(entry, 'arxiv_primary_category'):
                category = entry.arxiv_primary_category['term']
            else:
                category = 'Unknown'
            
            authors = [_maybe_clean_text(config, a.name) for a in entry.authors]
            author_threshold = get_config_value(
                config, "fetch.formatting.author_et_al_threshold", 1
            )
            if len(authors) > int(author_threshold):
                author_str = f"{authors[0]} et al."
            elif len(authors) == 1:
                author_str = authors[0]
            else:
                author_str = "Unknown"

            date_source = str(get_config_value(config, "fetch.formatting.date_source", "published") or "published").strip().lower()
            date_struct = None
            if date_source == "updated" and hasattr(entry, 'updated_parsed'):
                date_struct = entry.updated_parsed
            elif hasattr(entry, 'published_parsed'):
                date_struct = entry.published_parsed

            if date_struct:
                pub_date = datetime.date(*date_struct[:3]).strftime("%Y-%m-%d")
            else:
                pub_date = "Unknown Date"
            
            summary = _maybe_clean_text(config, entry.summary).replace('\n', ' ').strip()
            summary_max_chars = get_config_value(config, "fetch.formatting.summary_max_chars", 250)
            summary_hint = (
                summary[: int(summary_max_chars)] + "..."
                if len(summary) > int(summary_max_chars)
                else summary
            )
            
            papers.append({
                'title': title,
                'link': link,
                'arxiv_id': arxiv_id,
                'arxiv_version': arxiv_version,
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
    config = load_config(BASE_DIR)

    if not papers:
        print("没有论文更新")
        return

    inbox_rel = get_config_value(config, "paths.inbox", "Inbox.md")
    file_path = os.path.join(BASE_DIR, inbox_rel)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    existing_links = set()
    existing_versions_by_id = {}
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            existing_versions_by_id = _scan_existing_inbox_for_arxiv_versions(content)
            for m in re.finditer(r"\((https?://[^\)]+)\)", content):
                existing_links.add(m.group(1))

    archived_links, archived_versions_by_id = _scan_archived_index(config)

    # Merge: treat archived papers as already-known to avoid re-adding.
    known_links = set(existing_links) | set(archived_links)
    known_versions_by_id = dict(archived_versions_by_id)
    known_versions_by_id.update(existing_versions_by_id)

    dedupe_strategy = get_config_value(config, "fetch.dedupe.strategy", "link")
    version_behavior = str(
        get_config_value(config, "features.arxiv_version_update_behavior", "ignore")
    ).strip().lower()
    notice_tpl = get_config_value(
        config,
        "fetch.formatting.version_update_notice_template",
        "- [ ] (版本更新) {date}：{arxiv_id} 从 v{old_version} 更新到 v{new_version} - [{title}]({link})",
    )

    new_papers = []
    version_update_notices = []
    replacements = {}

    if str(dedupe_strategy).lower() == "arxiv_id":
        for p in papers:
            arxiv_id = p.get("arxiv_id")
            new_version = p.get("arxiv_version")

            if not arxiv_id:
                if p.get("link") and p["link"] not in known_links:
                    new_papers.append(p)
                continue

            old_version = known_versions_by_id.get(arxiv_id)

            if arxiv_id not in known_versions_by_id:
                new_papers.append(p)
                continue

            # If a paper is already archived (and not present in Inbox), avoid
            # re-introducing it via version update notices.
            if arxiv_id not in existing_versions_by_id and arxiv_id in archived_versions_by_id:
                continue

            if (
                version_behavior in {"append_notice", "replace"}
                and isinstance(new_version, int)
                and isinstance(old_version, int)
                and new_version > old_version
            ):
                if version_behavior == "replace":
                    replacements[arxiv_id] = new_version
                try:
                    version_update_notices.append(
                        notice_tpl.format(
                            date=today_str,
                            arxiv_id=arxiv_id,
                            title=p.get("title", ""),
                            link=p.get("link", ""),
                            old_version=old_version,
                            new_version=new_version,
                        )
                        + "\n"
                    )
                except Exception:
                    pass
    else:
        for p in papers:
            if p.get("link") and p["link"] not in known_links:
                new_papers.append(p)
    
    if not new_papers and not version_update_notices:
        print("没有论文更新")
        return

    if version_update_notices:
        print(f"检测到 {len(version_update_notices)} 条版本更新")
    if new_papers:
        print(f"获取到 {len(papers)} 篇论文. 其中{len(new_papers)} 篇是新的")
    
    new_lines = []
    heading_tpl = get_config_value(
        config,
        "fetch.formatting.daily_heading_template",
        "## {date} 更新 {count} 篇新论文",
    )
    new_lines.append(
        heading_tpl.format(date=today_str, count=(len(new_papers) + len(version_update_notices)))
        + "\n"
    )

    for notice in version_update_notices:
        new_lines.append(notice)

    item_tpl = get_config_value(
        config,
        "fetch.formatting.item_template",
        "- [ ] **[{category}]** [{title}]({link}) *by {author} ({published})* - _{summary}_",
    )
    for p in new_papers:
        line = item_tpl.format(
            category=p["category"],
            title=p["title"],
            link=p["link"],
            author=p["author"],
            published=p["published"],
            summary=p["summary"],
        )
        new_lines.append(line + "\n")
    new_lines.append("\n")

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    else:
        old_lines = ["# 📥 My Arxiv Inbox\n\n", "这里是你的待阅读区。\n\n", "---\n\n"]

    if replacements and os.path.exists(file_path):
        joined = "".join(old_lines)
        for base_id, latest_ver in replacements.items():
            pattern = re.compile(rf"https?://arxiv\\.org/abs/{re.escape(base_id)}(?:v\\d+)?")
            joined = pattern.sub(f"https://arxiv.org/abs/{base_id}v{latest_ver}", joined)
        old_lines = joined.splitlines(keepends=True)

    insert_index = -1
    delimiter = get_config_value(config, "fetch.formatting.inbox_insert_after_delimiter", "---")
    for i, line in enumerate(old_lines):
        if line.strip() == str(delimiter):
            insert_index = i + 1
            break
    
    if insert_index == -1:
        old_lines.append("\n---\n")
        insert_index = len(old_lines)

    final_lines = old_lines[:insert_index] + ["\n"] + new_lines + old_lines[insert_index:]

    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(final_lines)
    
    print(f"成功添加 {len(new_papers)} 篇论文、{len(version_update_notices)} 条版本提示 至 {file_path}")

if __name__ == "__main__":
    papers = fetch_papers()
    update_inbox(papers)
