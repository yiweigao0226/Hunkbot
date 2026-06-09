"""
SQLAlchemy ORM models for persisting review results.
"""
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo: Mapped[str] = mapped_column(String(255), index=True)
    pr_number: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id"))
    file: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(50))
    comment: Mapped[str] = mapped_column(Text)

    review: Mapped["Review"] = relationship(back_populates="comments")