"""Explicit, reversible preference learning and explainable paper ranking."""
import math
import re
from collections import Counter

STOP = set('the and for with from this that are was were have has into using based study paper model models approach results'.split())


def terms(text):
    return [t for t in re.findall(r'[a-z][a-z0-9-]{2,}|[\u4e00-\u9fff]{2,}', str(text).lower()) if t not in STOP]


def default_state():
    return {'version': 1, 'feedback': {}, 'runs': [], 'subscriptions': {}}


def feedback(state, paper_id, rating, text):
    if rating not in {'like', 'dislike', 'clear'}:
        raise ValueError('反馈须为 like、dislike 或 clear')
    if rating == 'clear':
        state['feedback'].pop(paper_id, None)
    else:
        if len(state['feedback']) >= 5000 and paper_id not in state['feedback']:
            raise ValueError('反馈已达 5000 条，请先清理旧反馈')
        state['feedback'][paper_id] = {'rating': rating, 'terms': dict(Counter(terms(text)).most_common(40))}


def rank(papers, interests, state, enabled=True):
    # Rebuild from explicit feedback on each run. Clearing a vote removes its effect.
    weights = Counter()
    for vote in state['feedback'].values():
        sign = 1 if vote['rating'] == 'like' else -1
        total = sum(vote['terms'].values()) or 1
        for term, count in vote['terms'].items():
            weights[term] += sign * count / total
    preferred = set(terms(' '.join(interests)))
    result = []
    for paper in papers:
        words = Counter(terms(paper.get('title', '') + ' ' + paper.get('summary', '')))
        overlap = sorted(preferred & words.keys())
        learned = sum(weights[t] * (1 + math.log(n)) for t, n in words.items())
        score = len(overlap) + learned
        own = state['feedback'].get(paper['arxiv_id'], {}).get('rating')
        if own == 'dislike':
            score -= 2
        elif own == 'like':
            score += 2
        influences = sorted((t for t in words if weights[t]), key=lambda t: -abs(weights[t]))[:5]
        result.append({**paper, 'score': round(score, 6), 'reasons': {
            'matched_interests': overlap, 'feedback_terms': influences,
            'feedback_contribution': round(learned, 6), 'explicit_feedback': own}})
    result.sort(key=lambda p: (str(p.get('published_at') or ''), p['arxiv_id']), reverse=True)
    if enabled:
        result.sort(key=lambda p: -p['score'])
    return result
