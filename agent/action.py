"""GitHub Actions entry point: publish the answer to the run summary only."""
import os
import sys
from pathlib import Path

from research_agent import run
from research_sources import normalize_id

SCENARIOS = {
    "论文检索": "按需检索收件箱、仓库论文和 arXiv，列出标题、作者、链接和相关性，注明来源和检索局限。",
    "阅读笔记": "检索相关论文和已有笔记，整理研究问题、方法、主要发现与局限，附来源；无法确认的内容标记待核验。",
    "文献综述": "检索相关论文和已有笔记，说明检索范围和方法，按主题比较研究脉络、方法及局限，生成带来源的综述草稿；不得虚构引用，证据不足时说明。",
}


def main() -> int:
    scenario = os.environ.get("RESEARCH_SCENARIO", "")
    question = os.environ.get("RESEARCH_QUESTION", "").strip()
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if scenario not in SCENARIOS or not question or not summary:
        print("缺少有效的研究场景、问题或 Actions 摘要路径", file=sys.stderr)
        return 1
    try:
        raw_ids = os.environ.get("RESEARCH_PAPER_IDS", "").strip()
        ids = [item.strip() for item in raw_ids.split(",")] if raw_ids else []
        if len(ids) > 10 or any(normalize_id(item) is None for item in ids):
            raise ValueError("论文 ID 须为逗号分隔的有效 arXiv ID，最多 10 个")
        budget_text = os.environ.get("RESEARCH_BUDGET", "1000000")
        if not budget_text.isascii() or not budget_text.isdigit() or len(budget_text) > 7:
            raise ValueError("token 预算须为 1 到 1000000 之间的整数")
        budget = int(budget_text)
        if not 1 <= budget <= 1_000_000:
            raise ValueError("token 预算须为 1 到 1000000 之间的整数")
        answer, used = run(SCENARIOS[scenario] + "\n用户问题：" + question, budget=budget, selected_ids=ids)
        # Mask the configured credential even if a provider unexpectedly echoes it.
        key = os.environ.get("key", "")
        if key:
            answer = answer.replace(key, "[已隐藏]")
        with Path(summary).open("a", encoding="utf-8") as output:
            output.write("## 研究助手结果\n\n" + answer + f"\n\n本次使用 {used} tokens。请核验来源及结论。\n")
    except (ValueError, RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
