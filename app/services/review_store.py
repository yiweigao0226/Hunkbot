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
from app.services.embedding_service import embed_text

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
    await db.flush()

    for c in result.comments:
        embedding = None
        try:
            embedding = await embed_text(f"{c.severity} {c.category}: {c.comment}")
        except Exception:
            logger.warning(f"Failed to embed comment for {repo} PR #{pr_number}, storing without embedding")

        db.add(ReviewComment(
            review_id=review.id,
            file=c.file,
            severity=c.severity,
            category=c.category,
            comment=c.comment,
            embedding=embedding,
        ))

    await db.commit()
    logger.info(f"Saved review for {repo} PR #{pr_number} — {len(result.comments)} comments")


async def get_repo_patterns(db: AsyncSession, repo: str, query_text: str = "", limit: int = 5) -> list[str]:
    # If we have a query and past comments have embeddings, use vector similarity search
    if query_text:
        try:
            query_embedding = await embed_text(query_text)
            result = await db.execute(
                select(
                    ReviewComment.comment,
                    ReviewComment.severity,
                    ReviewComment.category,
                )
                .join(Review)
                .where(Review.repo == repo)
                .where(ReviewComment.embedding.isnot(None))
                .order_by(ReviewComment.embedding.cosine_distance(query_embedding))
                .limit(limit)
            )
            rows = result.fetchall()
            if rows:
                return [
                    f"{severity.upper()} {category}: {comment}"
                    for comment, severity, category in rows
                ]
        except Exception:
            logger.warning(f"Vector search failed for {repo}, falling back to count-based patterns")

    # Fallback: count-based grouping (original approach)
    result = await db.execute(
        select(
            ReviewComment.category,
            ReviewComment.severity,
            func.count().label("count")
        )
        .join(Review)
        .where(Review.repo == repo)
        .group_by(ReviewComment.category, ReviewComment.severity)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = result.fetchall()

    if not rows:
        return []

    patterns = []
    for category, severity, count in rows:
        patterns.append(f"{severity.upper()} {category} issues have appeared {count} time(s) in this repo")

    return patterns