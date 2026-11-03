"""Validated settings shared by the runner and model client."""
from urllib.parse import urlsplit
import re

DEFAULTS = {
    'provider': 'deepseek', 'base_url': 'https://api.deepseek.com',
    'model': 'deepseek-flash', 'key_secret': 'key',
    'default_budget': 50000, 'max_budget': 1000000,
    'max_output_tokens': 4096, 'max_rounds': 12, 'timeout_seconds': 90,
}


def settings(config):
    agent = config.get('agent', {})
    if not isinstance(agent, dict):
        raise ValueError('agent 配置须为对象')
    raw = agent.get('runtime', {})
    if not isinstance(raw, dict):
        raise ValueError('agent.runtime 配置须为对象')
    preset = {'base_url': 'https://api.openai.com/v1', 'model': 'gpt-4.1-mini', 'key_secret': 'OPENAI_API_KEY'} if raw.get('provider') == 'openai' else {}
    result = {**DEFAULTS, **preset, **raw}
    if result['provider'] not in {'deepseek', 'openai', 'compatible'}:
        raise ValueError('供应商须为 deepseek、openai 或 compatible')
    url = result['base_url']
    if not isinstance(url, str):
        raise ValueError('服务地址须为 HTTPS URL')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('服务地址须为不带凭据、查询参数的 HTTPS URL')
    result['base_url'] = url.rstrip('/')
    if not isinstance(result['model'], str) or not result['model'].strip() or len(result['model']) > 150 or any(ord(c) < 32 for c in result['model']):
        raise ValueError('模型名称须为 1–150 字符')
    if not isinstance(result['key_secret'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,99}', result['key_secret']) or result['key_secret'].upper().startswith('GITHUB_'):
        raise ValueError('Actions secret 名称无效')
    for field, lower, upper in [('default_budget', 1, 1000000), ('max_budget', 1, 1000000), ('max_output_tokens', 128, 32768), ('max_rounds', 1, 24), ('timeout_seconds', 10, 180)]:
        if type(result[field]) is not int or not lower <= result[field] <= upper:
            raise ValueError(f'{field} 须为 {lower}–{upper} 之间的整数')
    if result['default_budget'] > result['max_budget']:
        raise ValueError('默认预算不能超过单任务预算上限')
    return result
