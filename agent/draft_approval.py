"""Explicit approval creates one review-note PR; it never merges or overwrites notes."""
import base64
import hashlib
import os
from pathlib import PurePosixPath
import re
from urllib.parse import quote


def _data(response, expected, message):
    if response.status_code not in expected:
        raise RuntimeError(message)
    try:
        return response.json()
    except ValueError:
        raise RuntimeError(message) from None


def _note_path(config, draft_id):
    paths = config.get('paths', {})
    if not isinstance(paths, dict):
        raise ValueError('笔记目录配置无效')
    value = paths.get('notes_dir', 'Notes')
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        raise ValueError('笔记目录须为仓库内相对路径')
    pieces = value.split('/')
    if any(not piece or piece in {'.', '..'} or piece.startswith('.') or not re.fullmatch(r'[\w .-]+', piece) for piece in pieces):
        raise ValueError('笔记目录包含不安全的路径')
    return str(PurePosixPath(value) / ('Research-' + draft_id + '.md'))


def _check_dirs(store, path, ref):
    # GitHub stores symlinks as content entries: do not follow a configured directory
    # that was replaced by a link or file. Nonexistent directories can be created by PUT.
    pieces = path.split('/')[:-1]
    for length in range(1, len(pieces) + 1):
        parent = '/'.join(pieces[:length])
        response = store.request('GET', '/contents/' + quote(parent, safe='/'), params={'ref': ref})
        if response.status_code == 404:
            return
        data = _data(response, {200}, '无法检查笔记目录')
        if not isinstance(data, list):
            raise ValueError('笔记目录是文件或符号链接，已停止保存')


def _same_note(store, path, ref, content):
    response = store.request('GET', '/contents/' + quote(path, safe='/'), params={'ref': ref})
    if response.status_code == 404:
        return False
    data = _data(response, {200}, '无法检查已有笔记')
    try:
        same = data.get('type') == 'file' and base64.b64decode(data['content'], validate=False) == content
    except (ValueError, KeyError, TypeError):
        same = False
    if not same:
        raise ValueError('目标笔记已存在且内容不同，已保留现有笔记')
    return True


def _existing_pr(store, head, base):
    owner = store.repo.split('/')[0]
    response = store.request('GET', '/pulls', params={'state': 'all', 'head': owner + ':' + head, 'base': base, 'per_page': 100})
    rows = _data(response, {200}, '无法检查已有PR')
    if not isinstance(rows, list):
        raise RuntimeError('已有 PR 响应格式无效')
    for row in rows:
        if row.get('head', {}).get('ref') == head and row.get('base', {}).get('ref') == base:
            return row
    return None


def approve(store, draft_id: str, root_config: dict) -> dict:
    if not isinstance(draft_id, str) or not re.fullmatch(r'[0-9]{1,24}-[0-9]{1,6}', draft_id):
        raise ValueError('草稿 ID 须为运行编号-尝试次数')
    state, _ = store.load()
    draft = state.get('drafts', {}).get(draft_id)
    if not isinstance(draft, dict) or not isinstance(draft.get('content'), str):
        raise ValueError('没有找到待确认的综述草稿')
    content = draft['content'].encode('utf-8')
    if not content or len(content) > 200_000:
        raise ValueError('草稿为空或超过 200 KB')
    digest = hashlib.sha256(content).hexdigest()
    if draft.get('sha256') != digest:
        raise ValueError('草稿摘要校验失败，已停止保存')
    for name in ('key', 'GH_TOKEN', 'GITHUB_TOKEN'):
        credential = os.environ.get(name)
        if credential and credential.encode('utf-8') in content:
            raise ValueError('草稿包含凭据内容，已拒绝保存')
    path = _note_path(root_config, draft_id)
    head = 'codex/research-note-' + draft_id
    repo = _data(store.request('GET', ''), {200}, '无法读取默认分支')
    base = repo.get('default_branch')
    if not isinstance(base, str) or not base:
        raise RuntimeError('仓库默认分支无效')
    base_ref = _data(store.request('GET', '/git/ref/heads/' + quote(base, safe='/')), {200}, '无法读取默认分支提交')
    sha = base_ref.get('object', {}).get('sha')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise RuntimeError('默认分支提交无效')
    _check_dirs(store, path, base)
    # Refuse to replace any differing file in the library, including symlinks.
    _same_note(store, path, base, content)
    ref = store.request('GET', '/git/ref/heads/' + head)
    if ref.status_code == 404:
        created = store.request('POST', '/git/refs', json={'ref': 'refs/heads/' + head, 'sha': sha})
        if created.status_code not in {201, 422}:
            raise RuntimeError('无法创建笔记草稿分支')
        # A 422 may be a racing creation. Read and verify branch content below.
        _data(store.request('GET', '/git/ref/heads/' + head), {200}, '无法确认笔记草稿分支')
    elif ref.status_code != 200:
        raise RuntimeError('无法读取笔记草稿分支')
    _check_dirs(store, path, head)
    before = _data(store.request('GET', '/compare/' + quote(base, safe='') + '...' + quote(head, safe='')), {200}, '无法检查已有草稿分支')
    if any(item.get('filename') != path for item in before.get('files', [])):
        raise ValueError('草稿分支包含其他变更，已停止保存')
    if not _same_note(store, path, head, content):
        # No SHA is supplied: concurrent file creation is rejected by the contents API.
        saved = store.request('PUT', '/contents/' + quote(path, safe='/'), json={
            'message': 'docs:保存已确认的研究笔记草稿', 'branch': head,
            'content': base64.b64encode(content).decode('ascii')})
        if saved.status_code not in {200, 201} and not _same_note(store, path, head, content):
            raise RuntimeError('无法保存研究笔记草稿')
    head_ref = _data(store.request('GET', '/git/ref/heads/' + head), {200}, '无法确认笔记分支提交')
    head_sha = head_ref.get('object', {}).get('sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', head_sha):
        raise RuntimeError('笔记分支提交无效')
    commit = _data(store.request('GET', '/git/commits/' + head_sha), {200}, '无法检查笔记文件模式')
    tree_sha = commit.get('tree', {}).get('sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', tree_sha):
        raise RuntimeError('笔记目录树无效')
    tree = _data(store.request('GET', '/git/trees/' + tree_sha, params={'recursive': '1'}), {200}, '无法检查笔记目录树')
    entry = next((item for item in tree.get('tree', []) if item.get('path') == path), None)
    if tree.get('truncated') or not entry or entry.get('type') != 'blob' or entry.get('mode') != '100644':
        raise ValueError('目标笔记不是普通文件或目录树不完整，已停止创建 PR')
    existing = _existing_pr(store, head, base)
    comparison = _data(store.request('GET', '/compare/' + quote(base, safe='') + '...' + quote(head, safe='')), {200}, '无法检查笔记草稿变更')
    files = comparison.get('files', [])
    if not files and existing and existing.get('merged_at'):
        return {'url': existing['html_url'], 'path': path, 'head': head}
    if len(files) != 1 or files[0].get('filename') != path or files[0].get('status') not in {'added', 'modified'}:
        raise ValueError('草稿分支包含其他变更，已停止创建 PR')
    if existing:
        return {'url': existing['html_url'], 'path': path, 'head': head}
    response = store.request('POST', '/pulls', json={
        'head': head, 'base': base, 'draft': False,
        'title': 'docs:保存研究笔记 ' + draft_id,
        'body': '用户通过 Research Agent 确认保存此综述草稿。所有结论仍需核验；本工作流不会合并 PR。\n\n草稿 SHA-256：' + digest})
    if response.status_code == 422:
        existing = _existing_pr(store, head, base)
        if existing:
            return {'url': existing['html_url'], 'path': path, 'head': head}
    created = _data(response, {201}, '无法创建笔记PR；请检查仓库是否允许 Actions 创建 PR')
    return {'url': created['html_url'], 'path': path, 'head': head}
