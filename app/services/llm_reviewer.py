"""
LLM review service.
- Builds a structured prompt from PRContext
- Calls LLM via provider-agnostic interface
- Returns a validated PRReviewResult
"""
import json
import logging

from app.core.models import PRContext, PRReviewResult
from app.services.llm_providers import get_provider

logger = logging.getLogger(__name__)


def _build_system_prompt(custom_rules: list[str], historical_patterns: list[str] = []) -> str:
    base = """You are an expert code reviewer. Your job is to review GitHub Pull Request diffs and provide actionable, precise feedback.

Review guidelines:
- Focus on bugs, security issues, and significant performance problems first
- Flag maintainability issues that will cause pain later
- Be concise: one comment per issue, no padding
- Reference the exact file and line number
- If no issues found in a file, don't manufacture feedback
- Prefer suggesting concrete fixes over vague criticism
- Do NOT report missing newlines at end of file — this is handled by formatters
- Do NOT report missing blank lines between classes/functions — style only
- Limit style comments to at most 1 per PR, only if critically unreadable

Severity definitions:
- error: Must be fixed before merging (bugs, security holes, broken logic)
- warning: Should be fixed (performance issues, edge cases, unclear code)
- suggestion: Nice to have (style, minor improvements, optional refactors)
"""

    if custom_rules:
        rules_text = "\n".join(f"- {r}" for r in custom_rules)
        base += f"\nProject-specific rules (treat violations as warnings):\n{rules_text}\n"

    if historical_patterns:
        patterns_text = "\n".join(f"- {p}" for p in historical_patterns)
        base += f"\nThis repo has a history of recurring issues. When you find similar problems, explicitly mention that this is a recurring pattern:\n{patterns_text}\n"

    return base


def _build_user_prompt(ctx: PRContext) -> str:
    lines = [
        f"## PR #{ctx.pr_number}: {ctx.pr_title}",
        f"**Repo**: {ctx.repo}  |  **Author**: {ctx.author}  |  **Branch**: `{ctx.head_branch}` → `{ctx.base_branch}`",
    ]

    if ctx.pr_description.strip():
        lines += ["", "**Description**:", ctx.pr_description]

    lines += ["", f"## Changed Files ({len(ctx.files)} files)", ""]

    for f in ctx.files:
        lang_tag = f.language or "diff"
        header = f"### `{f.filename}` ({f.status}, +{f.additions}/-{f.deletions})"
        lines += [
            header,
            f"```{lang_tag}",
            f.patch,
            "```",
            "",
        ]

    return "\n".join(lines)


async def review_pr(ctx: PRContext, historical_patterns: list[str] = []) -> PRReviewResult:
    """
    Send the PR context to the LLM and return a structured review result.
    Uses provider-agnostic interface — supports OpenAI and Anthropic.
    """
    system_prompt = _build_system_prompt(ctx.custom_rules, historical_patterns)
    user_prompt = _build_user_prompt(ctx)

    provider = get_provider()
    raw = await provider.complete(system_prompt, user_prompt)

    if isinstance(raw, PRReviewResult):
        return raw

    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    return PRReviewResult(**data)