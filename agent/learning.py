"""Explicit, reversible preference learning and explainable paper ranking."""
import math
import re
from collections import Counter

STOP = set('the and for with from this that are was were have has into using based study paper model models approach results'.split())
ID = re.compile(r'(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7})(?:v\d+)?', re.I)


def terms(text):
    result = []
    for word in re.findall(r'[a-z][a-z0-9-]{2,}|[\u4e00-\u9fff]{2,}', str(text).lower()):
        if word in STOP:
            continue
        if '\u4e00' <= word[0] <= '\u9fff':
            # Character bigrams let Chinese interest phrases match longer titles.
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            result.append(word)
    return result


def default_state():
    return {'version': 1, 'feedback': {}, 'runs': [], 'subscriptions': {}, 'drafts': {}, 'catalog': {}}


def feedback(state, paper_id, rating, text):
    if not isinstance(paper_id, str) or not ID.fullmatch(paper_id):
        raise ValueError('论文 ID 无效')
    paper_id = re.sub(r'v\d+$', '', paper_id.lower())
    if rating not in {'like', 'dislike', 'clear'}:
        raise ValueError('反馈须为 like、dislike 或 clear')
    if rating == 'clear':
        state['feedback'].pop(paper_id, None)
    else:
        if len(state['feedback']) >= 5000 and paper_id not in state['feedback']:
            raise ValueError('反馈已达 5000 条，请先清理旧反馈')
        if not isinstance(text, str) or len(text) > 100_000:
            raise ValueError('反馈论文内容无效或过长')
        state['feedback'][paper_id] = {'rating': rating, 'terms': dict(Counter(terms(text)).most_common(40))}


def rank(papers, interests, state, enabled=True):
    # Rebuild from explicit feedback on each run. Clearing a vote removes its effect.
    if not isinstance(interests, list) or len(interests) > 100 or any(not isinstance(item, str) or len(item) > 500 for item in interests):
        raise ValueError('兴趣须为最多 100 条文本，每条最多 500 字符')
    weights = Counter()
    for vote in state['feedback'].values():
        sign = 1 if vote['rating'] == 'like' else -1
        total = sum(vote['terms'].values()) or 1
        for term, count in vote['terms'].items():
            weights[term] += sign * count / total
    preferred = set(terms(' '.join(interests)))
    result = []
    for paper in papers:
        words = Counter(terms(str(paper.get('title') or '') + ' ' + str(paper.get('summary') or '')))
        overlap = sorted(preferred & words.keys())
        learned = sum(weights[t] * (1 + math.log(n)) for t, n in words.items())
        score = len(overlap) + learned
        paper_id = re.sub(r'v\d+$', '', paper['arxiv_id'].lower())
        own = state['feedback'].get(paper_id, {}).get('rating')
        if own == 'dislike':
            score -= 2
        elif own == 'like':
            score += 2
        influences = sorted((t for t in words if weights[t]), key=lambda t: (-abs(weights[t]), t))[:5]
        result.append({**paper, 'score': round(score, 6), 'reasons': {
            'matched_interests': overlap, 'feedback_terms': influences,
            'feedback_contribution': round(learned, 6), 'explicit_feedback': own,
            'positive_feedback_terms': [t for t in influences if weights[t] > 0],
            'negative_feedback_terms': [t for t in influences if weights[t] < 0]}})
    result.sort(key=lambda p: (str(p.get('published_at') or ''), p['arxiv_id']), reverse=True)
    if enabled:
        result.sort(key=lambda p: -p['score'])
    return result
