"""Persist learning state on a dedicated GitHub branch using optimistic writes."""
import base64
import copy
import hashlib
import json
import math
import os
import re
import time
from urllib.parse import quote

import requests
from learning import default_state, ID

# Keep the contents API's inline base64 representation available (< 1 MB).
MAX_STATE_BYTES = 900_000


def _json_shape(value, depth=0):
    if depth > 16:
        raise ValueError('研究状态嵌套过深')
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, list):
        for item in value:
            _json_shape(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _json_shape(item, depth + 1)
        return
    raise ValueError('研究状态包含无效 JSON 数据')


def validate_state(state):
    """Validate before either using or writing state; preserve extensible metadata."""
    if not isinstance(state, dict) or type(state.get('version')) is not int or state['version'] != 1:
        raise ValueError('研究状态版本无效')
    if not isinstance(state.get('feedback'), dict) or len(state['feedback']) > 5000:
        raise ValueError('论文反馈格式无效')
    if not isinstance(state.get('runs'), list) or not isinstance(state.get('subscriptions'), dict):
        raise ValueError('任务或订阅状态格式无效')
    # Version 1 originally lacked these optional collections.
    state.setdefault('drafts', {})
    state.setdefault('catalog', {})
    if not isinstance(state['drafts'], dict) or not isinstance(state['catalog'], dict):
        raise ValueError('草稿或论文目录格式无效')
    for paper_id, vote in state['feedback'].items():
        if not isinstance(paper_id, str) or not ID.fullmatch(paper_id) or not isinstance(vote, dict) or vote.get('rating') not in {'like', 'dislike'}:
            raise ValueError('论文反馈条目无效')
        counts = vote.get('terms')
        if not isinstance(counts, dict) or len(counts) > 40 or any(not isinstance(term, str) or not 1 <= len(term) <= 500 or type(count) is not int or not 1 <= count <= 100_000 for term, count in counts.items()):
            raise ValueError('论文反馈词权重无效')
    for run in state['runs']:
        if not isinstance(run, dict) or any(not isinstance(run.get(key), str) or not run[key] for key in ('id', 'operation', 'status')):
            raise ValueError('任务记录无效')
        for key in ('elapsed_seconds', 'used_tokens'):
            if key in run and (type(run[key]) not in (int, float) or not math.isfinite(run[key]) or run[key] < 0):
                raise ValueError('任务用量无效')
    for key, entry in state['subscriptions'].items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            raise ValueError('订阅记录无效')
        if 'seen' in entry and (not isinstance(entry['seen'], list) or any(not isinstance(item, str) for item in entry['seen'])):
            raise ValueError('订阅去重记录无效')
    for key, draft in state['drafts'].items():
        if not isinstance(key, str) or not isinstance(draft, dict) or not isinstance(draft.get('content'), str) or not re.fullmatch(r'[a-f0-9]{64}', str(draft.get('sha256', ''))):
            raise ValueError('综述草稿格式无效')
        if hashlib.sha256(draft['content'].encode()).hexdigest() != draft['sha256']:
            raise ValueError('综述草稿校验失败')
        if 'created_at' in draft and not isinstance(draft['created_at'], str):
            raise ValueError('综述草稿时间无效')
    for paper_id, paper in state['catalog'].items():
        if not isinstance(paper_id, str) or not ID.fullmatch(paper_id) or not isinstance(paper, dict) or any(key in paper and not isinstance(paper[key], str) for key in ('title', 'summary', 'authors', 'link', 'published_at', 'category')):
            raise ValueError('论文目录条目无效')
    _json_shape(state)
    return state


class StateStore:
    branch = 'agent-state'
    path = 'data/agent-state.json'

    def __init__(self):
        self.repo = os.environ.get('GITHUB_REPOSITORY', '')
        token = os.environ.get('GH_TOKEN', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', self.repo) or not token:
            raise ValueError('缺少 GitHub 仓库或状态存储令牌')
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'})
        self.base = 'https://api.github.com/repos/' + self.repo

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base + path, timeout=30, allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise RuntimeError('GitHub 状态存储网络请求失败') from None
        if response.status_code not in {200, 201, 202, 404, 409, 422}:
            raise RuntimeError('GitHub 状态存储请求失败（HTTP ' + str(response.status_code) + '）')
        return response

    def load(self):
        response = self.request('GET', '/contents/' + self.path, params={'ref': self.branch})
        if response.status_code == 404:
            return default_state(), None
        if response.status_code != 200:
            raise RuntimeError('无法读取研究状态')
        try:
            data = response.json()
            if data.get('encoding') not in (None, 'base64') or not isinstance(data.get('content'), str):
                raise ValueError
            raw = base64.b64decode(data['content'].replace('\n', ''), validate=True)
            if len(raw) > MAX_STATE_BYTES or not re.fullmatch(r'[a-f0-9]{40}', str(data.get('sha', ''))):
                raise ValueError
            state = validate_state(json.loads(raw))
            return state, data['sha']
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
            raise RuntimeError('研究状态格式无效，已停止以避免覆盖') from None

    def ensure_branch(self):
        branch = self.request('GET', '/git/ref/heads/' + self.branch)
        if branch.status_code == 200:
            return
        if branch.status_code != 404:
            raise RuntimeError('无法读取研究状态分支')
        repo = self.request('GET', '')
        if repo.status_code != 200:
            raise RuntimeError('无法读取仓库默认分支')
        default = repo.json().get('default_branch')
        if not isinstance(default, str) or not default:
            raise RuntimeError('仓库默认分支无效')
        main = self.request('GET', '/git/ref/heads/' + quote(default, safe=''))
        if main.status_code != 200:
            raise RuntimeError('无法读取仓库默认分支')
        result = self.request('POST', '/git/refs', json={'ref': 'refs/heads/' + self.branch, 'sha': main.json()['object']['sha']})
        if result.status_code == 201:
            return
        # A concurrent first run may have created it; do not treat every 422 as success.
        if result.status_code != 422 or self.request('GET', '/git/ref/heads/' + self.branch).status_code != 200:
            raise RuntimeError('无法初始化研究状态分支')

    def update(self, mutate):
        self.ensure_branch()
        for attempt in range(4):
            state, sha = self.load()
            updated = copy.deepcopy(state)
            mutate(updated)
            validate_state(updated)
            encoded = json.dumps(updated, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
            if len(encoded) > MAX_STATE_BYTES:
                raise ValueError('研究状态超过 900 KB，请清理旧草稿或目录后重试')
            payload = {'message': 'chore:更新研究助手状态', 'branch': self.branch,
                       'content': base64.b64encode(encoded).decode()}
            if sha:
                payload['sha'] = sha
            response = self.request('PUT', '/contents/' + self.path, json=payload)
            if response.status_code in {200, 201}:
                return updated
            if response.status_code not in {409, 422}:
                break
            time.sleep(0.2 * (attempt + 1))
        raise RuntimeError('研究状态更新冲突，请重新运行；现有状态未被覆盖')
