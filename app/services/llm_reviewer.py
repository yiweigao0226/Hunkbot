"""
LLM review service.
- Builds a structured prompt from PRContext
- Calls LLM via provider-agnostic interface (OpenAI or Anthropic)
- Implements retry logic for transient errors and validation failures
- Returns a validated PRReviewResult
"""
import asyncio
import json
import logging
from typing import Union

from pydantic import ValidationError

from app.core.models import PRContext, PRReviewResult
from app.services.llm_providers import get_provider

logger = logging.getLogger(__name__)

# One repair retry is a latency/token tradeoff: malformed JSON usually self-heals
# after one strict correction prompt; additional retries add delay with low gain.
SCHEMA_REPAIR_RETRIES = 1


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


def _build_schema_repair_prompt(user_prompt: str, error_msg: str) -> str:
    """Build a strict repair prompt after validation failure."""
    return f"""{user_prompt}

IMPORTANT: Your response must be ONLY valid JSON (no markdown, no extra text).
Previous parse error: {error_msg}
Ensure:
- All comments have exactly these fields: file, line, severity, category, comment
- severity must be exactly one of: error, warning, suggestion
- category must be exactly one of: bug, security, performance, style, maintainability
- line must be an integer
- Respond with ONLY the JSON object, nothing else.
"""


async def review_pr(ctx: PRContext, historical_patterns: list[str] = []) -> PRReviewResult:
    """
    Send the PR context to the LLM and return a structured review result.
    
     Retry strategy:
    1. OpenAI (structured output): Uses built-in validation; retries on transient errors
    2. Anthropic (JSON) or OpenAI validation failure: 
         - First attempt: try to parse and validate
         - If validation fails: SCHEMA_REPAIR_RETRIES repair attempt(s) with strict correction prompt
       - If still fails: raise with detailed error context
    """
    system_prompt = _build_system_prompt(ctx.custom_rules, historical_patterns)
    user_prompt = _build_user_prompt(ctx)

    provider = get_provider()
    raw = await provider.complete(system_prompt, user_prompt)

    # If OpenAI structured output (already validated during parse())
    if isinstance(raw, PRReviewResult):
        logger.info(f"Using OpenAI structured output: {len(raw.comments)} comments")
        return raw

    # Anthropic or fallback: JSON string parsing with retry on validation error
    try:
        return await _parse_and_validate_review(raw, user_prompt)
    except ValidationError as e:
        last_error = e
        for attempt in range(SCHEMA_REPAIR_RETRIES):
            logger.warning(
                "Validation error on attempt %s/%s; retrying with repair prompt",
                attempt + 1,
                SCHEMA_REPAIR_RETRIES,
            )
            repair_prompt = _build_schema_repair_prompt(user_prompt, str(last_error))
            repair_raw = await provider.complete(system_prompt, repair_prompt)

            if isinstance(repair_raw, PRReviewResult):
                return repair_raw

            try:
                return await _parse_and_validate_review(repair_raw, user_prompt, is_retry=True)
            except ValidationError as retry_error:
                last_error = retry_error

        raise last_error


async def _parse_and_validate_review(raw: str, context_prompt: str, is_retry: bool = False) -> PRReviewResult:
    """Parse JSON string and validate as PRReviewResult.
    
    Args:
        raw: JSON string from LLM
        context_prompt: User prompt (for error context)
        is_retry: Whether this is a retry attempt
    
    Raises:
        ValidationError: If parsing/validation fails
    """
    attempt_label = "(retry)" if is_retry else "(initial)"
    try:
        raw_clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw_clean)
        result = PRReviewResult(**data)
        logger.info(f"Successfully parsed review {attempt_label}: {len(result.comments)} comments")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error {attempt_label}: {e}")
        logger.error(f"Raw response: {raw[:500]}...")
        raise ValidationError.from_exception_data(
            "PRReviewResult",
            [{"loc": ("json",), "msg": f"Invalid JSON: {e}", "type": "value_error"}]
        )
    except ValidationError as e:
        logger.error(f"Pydantic validation error {attempt_label}: {e}")
        logger.error(f"Parsed data: {raw[:500]}...")
        raise