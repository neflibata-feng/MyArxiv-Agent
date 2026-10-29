"""Read workflow status and explicitly retry failed jobs in two approved workflows."""
from datetime import datetime
import os
import re

ALLOWED_WORKFLOWS = {
    '.github/workflows/daily_scheduler.yml',
    '.github/workflows/auto_archive.yml',
}
RETRY_CONCLUSIONS = {'failure', 'timed_out', 'cancelled'}
RUNNING = {'queued', 'in_progress', 'waiting', 'pending', 'requested'}


def _read(response, message):
    if response.status_code != 200:
        raise RuntimeError(message)
    try:
        value = response.json()
    except ValueError:
        raise RuntimeError(message) from None
    if not isinstance(value, dict):
        raise RuntimeError(message)
    return value


def _text(value, limit=160):
    text = str(value or '').replace('\r', ' ').replace('\n', ' ')
    for name in ('key', 'GH_TOKEN', 'GITHUB_TOKEN'):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, '[已隐藏]')
    text = text[:limit]
    return re.sub(r'([\\`*_{}\[\]<>#|])', r'\\\1', text)


def _duration(run):
    try:
        start = datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
        seconds = max(0, int((end - start).total_seconds()))
        return str(seconds) + ' 秒'
    except (KeyError, ValueError, TypeError, AttributeError):
        return '—'


def _job_failures(store, run_id):
    try:
        jobs = _read(store.request('GET', f'/actions/runs/{run_id}/jobs', params={'per_page': 100}), '无法读取工作流步骤')
    except RuntimeError:
        return '失败步骤暂不可读'
    details = []
    rows = jobs.get('jobs')
    if not isinstance(rows, list):
        return '失败步骤响应格式无效'
    for job in rows[:100]:
        if not isinstance(job, dict) or job.get('conclusion') not in RETRY_CONCLUSIONS:
            continue
        job_steps = job.get('steps')
        steps = [step for step in job_steps if isinstance(step, dict) and step.get('conclusion') in RETRY_CONCLUSIONS] if isinstance(job_steps, list) else []
        if steps:
            details.extend(_text(job.get('name'), 60) + ' / ' + _text(step.get('name'), 100) for step in steps[:10])
        else:
            details.append(_text(job.get('name'), 60) + '（' + _text(job.get('conclusion')) + '）')
        if len(details) >= 10:
            break
    if type(jobs.get('total_count')) is int and jobs['total_count'] > 100:
        details.append('仅展示前 100 个 job')
    return '；'.join(details[:11]) or '没有返回失败步骤'


def inspect(store):
    """Show the latest 30 runs, failed step names and our explicit retry records."""
    payload = _read(store.request('GET', '/actions/runs', params={'per_page': 30}), '无法读取工作流任务列表')
    runs = payload.get('workflow_runs')
    if not isinstance(runs, list):
        raise RuntimeError('工作流任务列表格式无效')
    lines = ['## GitHub Actions 任务中心', '',
             '| 任务 | 状态 / 结果 | 尝试 | 耗时 | 失败步骤 |',
             '| --- | --- | --- | --- | --- |']
    for run in runs[:30]:
        if not isinstance(run, dict) or type(run.get('id')) is not int or run['id'] <= 0:
            continue
        run_id = run['id']
        url = f'https://github.com/{store.repo}/actions/runs/{run_id}'
        failure = _job_failures(store, run_id) if run.get('conclusion') in RETRY_CONCLUSIONS else '—'
        title = _text(run.get('name') or run.get('path') or run_id)
        status = _text(run.get('status')) + ' / ' + _text(run.get('conclusion') or '—')
        attempt = run.get('run_attempt', 1)
        attempt = str(attempt) if type(attempt) is int and attempt > 0 else '—'
        lines.append(f'| [{title}]({url}) | {status} | {attempt} | {_duration(run)} | {failure} |')
    if not runs:
        lines.append('| 尚无工作流任务 | — | — | — | — |')
    lines.extend(['', '耗时按运行开始与最近更新时间计算；进行中的任务尚未结束。',
                  '失败详情仅显示 job 和步骤名称，不读取日志。手动重试目标格式为 `actions:运行编号`。', '', '### 手动重试记录', ''])
    try:
        state, _ = store.load()
        history = state.get('runs', [])
    except (AttributeError, RuntimeError, TypeError):
        history = []
        lines.append('研究状态中的重试记录暂不可读。')
    retries = [item for item in history if isinstance(item, dict) and
               (item.get('operation') == 'retry' or item.get('requested_operation') == 'retry')][-20:]
    for item in reversed(retries):
        trace = item.get('trace') if isinstance(item.get('trace'), dict) else {}
        inputs = item.get('inputs') if isinstance(item.get('inputs'), dict) else {}
        # For research retries inputs contain the effective request, whose target
        # may be empty or a subscription ID. The trace identifies the retried run.
        target = (trace.get('retry_of') or inputs.get('target') or item.get('target') or
                  item.get('target_run_id') or item.get('target_id') or '—')
        lines.append('- ' + _text(item.get('id')) + '：' + _text(target) + '，' + _text(item.get('status')))
    if not retries:
        lines.append('暂无通过研究助手发起的重试记录；Actions 的尝试次数显示在上表。')
    return '\n'.join(lines) + '\n'


def retry_workflow(store, run_id):
    """Retry failed jobs only after an explicit actions:ID request; never rerun PR code."""
    if not isinstance(run_id, str) or not re.fullmatch(r'actions:[1-9][0-9]{0,19}', run_id):
        raise ValueError('工作流重试目标须为 actions:运行编号')
    number = int(run_id.split(':', 1)[1])
    path = f'/actions/runs/{number}'
    run = _read(store.request('GET', path), '无法读取待重试工作流')
    repository = run.get('repository', {})
    head_repository = run.get('head_repository')
    if not isinstance(repository, dict) or str(repository.get('full_name', '')).lower() != store.repo.lower():
        raise ValueError('工作流不属于当前仓库')
    if head_repository is not None and (not isinstance(head_repository, dict) or str(head_repository.get('full_name', '')).lower() != store.repo.lower()):
        raise ValueError('不重试来自其他仓库的代码')
    if type(run.get('id')) is not int or run['id'] != number or run.get('path') not in ALLOWED_WORKFLOWS:
        raise ValueError('仅允许重试论文抓取或归档工作流')
    repo = _read(store.request('GET', ''), '无法确认默认分支')
    if not repo.get('default_branch') or run.get('head_branch') != repo['default_branch'] or run.get('event') not in {'push', 'schedule', 'workflow_dispatch'}:
        raise ValueError('仅允许重试默认分支上的抓取或归档任务')
    result = {'run_id': number, 'workflow': run['path'], 'url': f'https://github.com/{store.repo}/actions/runs/{number}'}
    if run.get('status') in RUNNING:
        return {**result, 'status': 'already_running'}
    if run.get('status') != 'completed' or run.get('conclusion') not in RETRY_CONCLUSIONS:
        raise ValueError('仅允许重试失败、超时或已取消的任务')
    response = store.request('POST', path + '/rerun-failed-jobs')
    if response.status_code == 202:
        return {**result, 'status': 'requested'}
    if response.status_code in {409, 422}:
        current = _read(store.request('GET', path), '无法确认工作流重试状态')
        if current.get('status') in RUNNING:
            return {**result, 'status': 'already_running'}
    raise RuntimeError('重试未被 GitHub 接受，请检查工作流状态和 Actions 写入权限')
