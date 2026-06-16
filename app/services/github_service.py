"""
GitHub App authentication and comment posting.

GitHub App auth flow:
1. Sign a JWT with the App's private key
2. Use JWT to get an installation access token (scoped to a repo)
3. Use that token to make API calls via PyGithub

This is more secure than OAuth tokens and is the standard for bots.
"""
import base64
import os
import time

import httpx
import jwt
from github import Github
from github.PullRequest import PullRequest

from app.core.config import settings
from app.core.models import PRReviewResult


def _get_installation_token(installation_id: int) -> str:
    """
    Generate a short-lived installation access token for the given installation.
    Valid for 1 hour (GitHub limit).
    """
    key_base64 = os.environ.get("GITHUB_PRIVATE_KEY_BASE64")
    if key_base64:
        private_key = base64.b64decode(key_base64).decode("utf-8")
    else:
        with open(settings.github_private_key_path, "r") as f:
            private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now - 60, 
        "exp": now + 300, 
        "iss": settings.github_app_id,
    }
    jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

    response = httpx.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    response.raise_for_status()
    return response.json()["token"]


def get_github_client(installation_id: int) -> Github:
    """Return an authenticated PyGithub client for this installation."""
    token = _get_installation_token(installation_id)
    return Github(token)


def post_review(pr: PullRequest, result: PRReviewResult) -> None:
    """
    Post the LLM review result as a GitHub PR review.
    - Uses GitHub's createReview API to batch all comments in one call
    - Sets the review state: APPROVE, REQUEST_CHANGES, or COMMENT
    """
    if result.approved and not any(c.severity == "error" for c in result.comments):
        event = "APPROVE"
    elif any(c.severity == "error" for c in result.comments):
        event = "REQUEST_CHANGES"
    else:
        event = "COMMENT"

    commit = pr.get_commits().reversed[0]

    severity_emoji = {"error": "🔴", "warning": "🟡", "suggestion": "💡"}

    review_body = f"## AI Code Review\n\n{result.summary}\n\n"

    if result.comments:
        review_body += f"### Issues Found ({len(result.comments)})\n\n"
        for c in result.comments:
            emoji = severity_emoji[c.severity]
            review_body += f"**{emoji} {c.category.upper()}** — `{c.file}` line {c.line}\n\n"
            review_body += f"{c.comment}\n\n"
            if c.recurring_note:
                review_body += f"⚠️ **Recurring pattern** {c.recurring_note}\n\n"
            if c.suggestion:
                review_body += f"**Suggestion:**\n```\n{c.suggestion}\n```\n\n"
            review_body += "---\n\n"

    pr.create_review(
        commit=commit,
        body=review_body,
        event=event,
        comments=[], 
    )