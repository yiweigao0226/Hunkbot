"""
Persist review results to PostgreSQL and retrieve historical patterns per repo.
Used for per-repo learning — historical bug patterns are injected into LLM prompt
to improve review quality over time.
"""
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models_db import Review, ReviewComment
from app.core.models import PRReviewResult

logger = logging.getLogger(__name__)


async def save_review(db: AsyncSession, repo: str, pr_number: int, result: PRReviewResult) -> None:
    """Persist a completed review result to the database."""
    review = Review(
        repo=repo,
        pr_number=pr_number,
        summary=result.summary,
        approved=result.approved,
    )
    db.add(review)
    await db.flush()  # get review.id without committing

    for c in result.comments:
        db.add(ReviewComment(
            review_id=review.id,
            file=c.file,
            severity=c.severity,
            category=c.category,
            comment=c.comment,
        ))

    await db.commit()
    logger.info(f"Saved review for {repo} PR #{pr_number} — {len(result.comments)} comments")


async def get_repo_patterns(db: AsyncSession, repo: str, limit: int = 5) -> list[str]:
    """
    Retrieve the most common issue categories and examples from past reviews for a repo.
    Returns a list of pattern strings to inject into the LLM prompt.
    """
    # Get most frequent categories for this repo
    result = await db.execute(
        select(ReviewComment.category, ReviewComment.comment)
        .join(Review)
        .where(Review.repo == repo)
        .order_by(func.random())
        .limit(limit)
    )
    rows = result.fetchall()

    if not rows:
        return []

    patterns = []
    for category, comment in rows:
        patterns.append(f"[{category.upper()}] {comment}")

    return patterns