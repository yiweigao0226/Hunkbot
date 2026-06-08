"""
Diff processing: fetch PR files from GitHub and prepare them for LLM review.
Key decisions:
- Skip binary files, lock files, and auto-generated code
- Truncate large files to stay within LLM context window
- Infer language from file extension for better LLM prompting
"""
import re
from pathlib import Path

from github.PullRequest import PullRequest
from github.File import File

from app.core.config import settings
from app.core.models import FileDiff, PRContext


# Files to skip entirely — not useful for code review
SKIP_PATTERNS = [
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"Pipfile\.lock$",
    r"poetry\.lock$",
    r"\.min\.(js|css)$",
    r"dist/",
    r"build/",
    r"__pycache__/",
    r"\.pb\.go$",        # protobuf generated
    r"_pb2\.py$",        # protobuf generated
    r"migrations/\d+",  # DB migrations (too noisy)
]

EXTENSION_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript/React", ".jsx": "JavaScript/React",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
    ".swift": "Swift", ".cpp": "C++", ".c": "C", ".cs": "C#",
    ".rb": "Ruby", ".php": "PHP", ".sh": "Shell",
    ".yml": "YAML", ".yaml": "YAML", ".json": "JSON",
    ".sql": "SQL", ".md": "Markdown",
}


def _should_skip(filename: str) -> bool:
    return any(re.search(pattern, filename) for pattern in SKIP_PATTERNS)


def _infer_language(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, "")


def _truncate_patch(patch: str, max_lines: int) -> str:
    """Keep first max_lines of a diff patch, adding a notice if truncated."""
    if not patch:
        return ""
    lines = patch.splitlines()
    if len(lines) <= max_lines:
        return patch
    truncated = lines[:max_lines]
    truncated.append(f"... [truncated: {len(lines) - max_lines} more lines not shown] ...")
    return "\n".join(truncated)


def process_pr_files(pr: PullRequest, custom_rules: list[str] = []) -> PRContext:
    """
    Fetch all changed files from a PR and build a PRContext ready for LLM review.
    Applies file filtering and truncation according to settings.
    """
    files: list[File] = list(pr.get_files())

    # Warn if too many files — still process up to the limit
    if len(files) > settings.max_files_per_pr:
        files = files[: settings.max_files_per_pr]

    processed: list[FileDiff] = []
    for f in files:
        if _should_skip(f.filename):
            continue
        if f.status == "removed":
            continue  # No point reviewing deleted files
        if not f.patch:
            continue  # Binary file or empty diff

        patch = _truncate_patch(f.patch, settings.max_lines_per_file)
        processed.append(
            FileDiff(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=patch,
                language=_infer_language(f.filename),
            )
        )

    body = pr.body or ""
    return PRContext(
        repo=pr.base.repo.full_name,
        pr_number=pr.number,
        pr_title=pr.title,
        pr_description=body[:1000],  # cap description length
        author=pr.user.login,
        base_branch=pr.base.ref,
        head_branch=pr.head.ref,
        files=processed,
        custom_rules=custom_rules,
    )
