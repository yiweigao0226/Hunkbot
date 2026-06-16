from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------- LLM Output Schema ----------

class ReviewComment(BaseModel):
    """A single inline comment on the PR diff."""
    file: str = Field(description="Relative file path, e.g. src/auth/login.py")
    line: int = Field(description="Line number in the NEW file (after changes)")
    severity: Literal["error", "warning", "suggestion"] = Field(
        description="error=must fix, warning=should fix, suggestion=nice to have"
    )
    category: Literal["bug", "security", "performance", "style", "maintainability"] = Field(
        description="Type of issue found"
    )
    comment: str = Field(description="Clear explanation of the issue")
    suggestion: Optional[str] = Field(
        default=None,
        description="Concrete fix or improved code snippet if applicable"
    )
    recurring_note: Optional[str] = Field(
        default=None,
        description="Set if a similar issue was found in past reviews of this repo"
    )


class PRReviewResult(BaseModel):
    """Complete review result returned by LLM."""
    summary: str = Field(description="2-3 sentence overall assessment of the PR")
    comments: list[ReviewComment] = Field(
        default_factory=list,
        description="List of specific inline comments. Empty list if no issues found."
    )
    approved: bool = Field(
        description="True if PR looks good overall (warnings/suggestions OK), False if errors exist"
    )


# ---------- Internal Models ----------

class FileDiff(BaseModel):
    """Processed diff for a single file."""
    filename: str
    status: str         
    additions: int
    deletions: int
    patch: str         
    language: str = ""  


class PRContext(BaseModel):
    """All context passed to the LLM for review."""
    repo: str
    pr_number: int
    pr_title: str
    pr_description: str
    author: str
    base_branch: str
    head_branch: str
    files: list[FileDiff]
    custom_rules: list[str] = Field(default_factory=list)
