"""Render structured research claims with only retrieved references and explicit uncertainty."""
import json
import re

from research_sources import normalize_id

PROMPT = '''输出 JSON 对象，格式 {"title":"...","scope":"检索范围及局限","sections":[{"heading":"...","claims":[{"text":"一个结论或比较","source_ids":["arxiv基础ID"]}]}]}。
先检索证据，再按主题比较方法、结果和局限。source_ids 只能使用本次工具实际取得的论文 ID。证据不足时保留空数组。禁止在 text 中写 URL、Markdown 链接或虚构数字；所有结论都将标为待人工核验。说明仅摘要或全文依据，不把摘要当全文。'''


def plain(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('综述字段为空或过长')
    if re.search(r'https?://|www\.|\]\(', value, re.I):
        raise ValueError('综述文本须通过结构化来源引用')
    # Escape Markdown/HTML to keep source links separate from model prose.
    return re.sub(r'([\\`*_{}\[\]<>#|])', r'\\\1', value.strip()).replace('\n', ' ')


def render(raw, sources):
    data = json.loads(raw)
    known = set(sources)
    title, scope = plain(data['title'], 200), plain(data['scope'], 2000)
    sections = data['sections']
    if not isinstance(sections, list) or not 1 <= len(sections) <= 12:
        raise ValueError('综述章节数量无效')
    lines = ['# ' + title, '', '> 草稿：所有结论待人工核验；引用只证明本次检索取得了对应记录。', '', '检索范围：' + scope]
    used = set()
    for section in sections:
        lines += ['', '## ' + plain(section['heading'], 120), '']
        claims = section['claims']
        if not isinstance(claims, list) or not 1 <= len(claims) <= 20:
            raise ValueError('综述结论数量无效')
        for claim in claims:
            text = plain(claim['text'], 2000)
            ids = claim['source_ids']
            if not isinstance(ids, list) or len(ids) > 10:
                raise ValueError('来源列表无效')
            normalized = [normalize_id(x) for x in ids]
            if any(x is None or x not in known for x in normalized):
                raise ValueError('综述引用了未检索到的论文，草稿未保存')
            used.update(normalized)
            refs = ' '.join('[来源 ' + i + '](https://arxiv.org/abs/' + i + ')' for i in sorted(set(normalized)))
            lines.append('- ' + text + ' **[待核验' + ('' if ids else '；缺少来源') + ']** ' + refs)
    lines += ['', '## 来源', ''] + ['- https://arxiv.org/abs/' + i for i in sorted(used)]
    return '\n'.join(lines) + '\n'
