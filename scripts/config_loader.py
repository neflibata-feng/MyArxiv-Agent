from __future__ import annotations

import os
from typing import Any, Dict

import yaml


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _set_nested(config: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split("__") if p]
    cur: Dict[str, Any] = config
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if parts:
        cur[parts[-1]] = value


def _parse_env_value(raw: str) -> Any:
    v = raw.strip()
    lower = v.lower()
    if lower in {"true", "false"}:
        return lower == "true"

    try:
        if lower.startswith("0") and len(lower) > 1 and lower[1].isdigit():
            raise ValueError
        return int(v)
    except ValueError:
        pass

    try:
        return float(v)
    except ValueError:
        pass

    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        try:
            loaded = yaml.safe_load(v)
            return loaded
        except Exception:
            return v

    return v


def load_config(base_dir: str) -> Dict[str, Any]:
    """Load root config.yaml with env overrides.

    Env override format:
      - Prefix: ARXIV_AGENT__
      - Nested keys separated by double underscore.
    Example:
      ARXIV_AGENT__fetch__arxiv_api__max_results=200
      ARXIV_AGENT__fetch__query__categories=["cs.AI","cs.CL"]
    """

    config_path = os.path.join(base_dir, "config.yaml")

    file_config: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                file_config = loaded

    env_override: Dict[str, Any] = {}
    prefix = "ARXIV_AGENT__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        path = key[len(prefix) :]
        # normalize path to lower-case keys to match yaml convention
        path = "__".join([p.lower() for p in path.split("__") if p])
        _set_nested(env_override, path, _parse_env_value(value))

    return _deep_merge_dict(file_config, env_override)


def get_config_value(config: Dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    cur: Any = config
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
