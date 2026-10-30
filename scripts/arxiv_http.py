"""Polite arXiv transport shared by fetching and research within one process."""
import math
import random
import threading
import time
from email.utils import parsedate_to_datetime

import requests

DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 MyArxiv-Agent/1.0 (contact: https://github.com/neflibata-feng)'

_session = requests.Session()
_lock = threading.Lock()
_not_before = 0.0


class ArxivRateLimitError(RuntimeError):
    def __init__(self, message, retry_after_seconds=300):
        super().__init__(message)
        self.retry_after_seconds = max(300, math.ceil(retry_after_seconds))


def user_agent(value=None):
    value = str(value or '').strip()
    if not value or value in {
        'MyArxiv-Agent/1.0 (+https://github.com/)',
        'MyArxiv-Agent/1.0 (research workflow)',
        'MyArxiv-Agent/1.0 (arXiv metadata sync; contact: https://github.com/neflibata-feng)',
    }:
        return DEFAULT_USER_AGENT
    if len(value) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('arXiv User-Agent 无效')
    return value


def retry_after(response):
    value = response.headers.get('Retry-After', '').strip() if response is not None else ''
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            seconds = parsedate_to_datetime(value).timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def backoff(attempt, base, response=None):
    # A 429 requires a longer pause than a normal network retry.
    floor = 30 if response is not None and response.status_code == 429 else 3
    delay = max(floor, float(base) * (2 ** attempt))
    delay += random.uniform(0, min(5, delay * 0.25))
    return max(delay, retry_after(response) or 0)


def cooldown_seconds():
    return max(300, math.ceil(_not_before - time.monotonic()))


def get(url, *, params, timeout=30, headers=None, stream=False, min_delay=3, **kwargs):
    global _not_before
    with _lock:
        wait = _not_before - time.monotonic()
        if wait > 120:
            raise ArxivRateLimitError('arXiv 尚在服务端冷却期，暂停请求', wait)
        if wait > 0:
            time.sleep(wait)
        # Record before the request, so connection and read timeouts are paced too.
        _not_before = time.monotonic() + max(3, float(min_delay))
        request_headers = {**(headers or {}), 'User-Agent': user_agent((headers or {}).get('User-Agent')), 'Accept': 'application/atom+xml'}
        response = _session.get(url, params=params, timeout=timeout, headers=request_headers,
                                stream=stream, allow_redirects=False, **kwargs)
        if response.status_code in {429, 503}:
            delay = retry_after(response)
            if response.status_code == 429 or delay is not None:
                _not_before = max(_not_before, time.monotonic() + (delay if delay is not None else 30))
        return response
