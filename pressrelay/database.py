import enum
from datetime import datetime
from typing import Any, Dict, Optional, List

from sqlalchemy import Column, String, Integer, DateTime, JSON, Enum, ForeignKey, Index
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# 1. New Enums and Statuses
class ArticleStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Base(DeclarativeBase):
    pass


# 2. Schema Models
class Feed(Base):
    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String)
    last_fetch_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationship to articles
    articles: Mapped[List["Article"]] = relationship(back_populates="feed", cascade="all, delete-orphan")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    source_feed: Mapped[str] = mapped_column(String)  # For backward compatibility/legacy
    
    # New Fields
    status: Mapped[ArticleStatus] = mapped_column(Enum(ArticleStatus), default=ArticleStatus.PENDING)
    content_hash: Mapped[Optional[str]] = mapped_column(String, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Rich Storage
    markdown_path: Mapped[Optional[str]] = mapped_column(String)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    
    # Link to Feed table
    feed_id: Mapped[Optional[int]] = mapped_column(ForeignKey("feeds.id"))
    feed: Mapped[Optional[Feed]] = relationship(back_populates="articles")

    # Composite Index for faster lookups
    __table_args__ = (
        Index("ix_article_url_status", "url", "status"),
    )


# 3. Database Connection Utility
async def get_db_engine(db_url: str):
    return create_async_engine(db_url, echo=False)


def get_session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_db_and_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
