"""Persist learning state on a dedicated GitHub branch using optimistic writes."""
import copy
import json
import os
import re
import time

import requests
from learning import default_state


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
        response = self.session.request(method, self.base + path, timeout=30, allow_redirects=False, **kwargs)
        if response.status_code not in {200, 201, 404, 409, 422}:
            raise RuntimeError('GitHub 状态存储请求失败（HTTP ' + str(response.status_code) + '）')
        return response

    def load(self):
        import base64
        response = self.request('GET', '/contents/' + self.path, params={'ref': self.branch})
        if response.status_code == 404:
            return default_state(), None
        if response.status_code != 200:
            raise RuntimeError('无法读取研究状态')
        try:
            data = response.json()
            state = json.loads(base64.b64decode(data['content']))
            if state.get('version') != 1 or not isinstance(state.get('feedback'), dict) or not isinstance(state.get('runs'), list) or not isinstance(state.get('subscriptions'), dict):
                raise ValueError
            return state, data['sha']
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('研究状态格式无效，已停止以避免覆盖') from None

    def ensure_branch(self):
        branch = self.request('GET', '/git/ref/heads/' + self.branch)
        if branch.status_code == 200:
            return
        repo = self.request('GET', '').json()
        main = self.request('GET', '/git/ref/heads/' + repo['default_branch']).json()
        result = self.request('POST', '/git/refs', json={'ref': 'refs/heads/' + self.branch, 'sha': main['object']['sha']})
        if result.status_code not in {201, 422}:
            raise RuntimeError('无法初始化研究状态分支')

    def update(self, mutate):
        import base64
        self.ensure_branch()
        for attempt in range(4):
            state, sha = self.load()
            updated = copy.deepcopy(state)
            mutate(updated)
            encoded = json.dumps(updated, ensure_ascii=False, sort_keys=True).encode()
            if len(encoded) > 2_000_000:
                raise ValueError('研究状态超过 2 MB')
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
