import asyncio
import os
import re
import hashlib
import feedparser
from datetime import datetime
from time import mktime
from typing import Optional, Callable
import httpx
import aiofiles

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pressrelay.logger import logger
from pressrelay.database import Article, ArticleStatus, Feed
from pressrelay.processing import fetch_and_convert_to_markdown
from pressrelay.config import AppConfig, FeedConfig

def slugify(text: str) -> str:
    """Convert a string to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W-]+', '-', text)
    return text.strip('-')

def get_content_hash(content: str) -> str:
    """Generate a SHA256 hash of the content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

async def process_and_save_article(
    entry: dict, 
    feed_cfg: FeedConfig, 
    client: httpx.AsyncClient, 
    app_config: AppConfig,
    session_factory: Callable[[], AsyncSession]
):
    """Processes a single article entry: fetches, converts, and saves with V2 logic."""
    article_url = entry.get('link')
    if not article_url:
        return

    async with session_factory() as session:
        # 1. Check if article already exists in the DB
        stmt = select(Article).where(Article.url == article_url)
        result = await session.execute(stmt)
        existing_article = result.scalars().first()
        
        if existing_article and existing_article.status == ArticleStatus.SUCCESS:
            return  # Already processed successfully

        logger.info(f"New article found: '{entry.get('title', 'No Title')}'")

        # 2. Fetch and convert the article content
        markdown_content, metadata = await fetch_and_convert_to_markdown(article_url, client)
        
        if not markdown_content:
            # Create a failed record if it doesn't exist
            if not existing_article:
                failed_article = Article(
                    title=entry.get('title', 'Unknown'),
                    url=article_url,
                    source_feed=feed_cfg.url,
                    status=ArticleStatus.FAILED
                )
                session.add(failed_article)
                await session.commit()
            return

        # 3. Determine metadata and hashes
        content_hash = get_content_hash(markdown_content)
        published_at = datetime.utcnow()
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published_at = datetime.fromtimestamp(mktime(entry.published_parsed))

        # 4. Save markdown file (V2 hashed structure: ab/cd/hash-slug.md)
        # Using first 4 chars of hash for a 2-level nest
        h = content_hash
        hash_dir = app_config.storage_path / h[0:2] / h[2:4]
        hash_dir.mkdir(parents=True, exist_ok=True)
        
        article_slug = slugify(entry.get('title', 'article'))
        filename = f"{h[:10]}-{article_slug[:80]}.md"
        file_path = hash_dir / filename

        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(markdown_content)
        except IOError as e:
            logger.error(f"Error saving markdown file {file_path}: {e}")
            return

        # 5. Update or Create Article record
        if existing_article:
            existing_article.status = ArticleStatus.SUCCESS
            existing_article.content_hash = content_hash
            existing_article.published_at = published_at
            existing_article.markdown_path = str(file_path)
            existing_article.processed_at = datetime.utcnow()
            existing_article.metadata_json = metadata or {}
        else:
            new_article = Article(
                title=entry.get('title', 'Unknown'),
                url=article_url,
                source_feed=feed_cfg.url,
                status=ArticleStatus.SUCCESS,
                content_hash=content_hash,
                published_at=published_at,
                markdown_path=str(file_path),
                processed_at=datetime.utcnow(),
                metadata_json=metadata or {}
            )
            session.add(new_article)
            
        await session.commit()
        logger.success(f"Successfully saved article: {entry.get('title')}")

async def feed_processing_loop(
    feed_cfg: FeedConfig, 
    app_config: AppConfig,
    session_factory: Callable[[], AsyncSession],
    client: httpx.AsyncClient
):
    """Infinite loop for fetching and processing a single RSS feed."""
    
    while True:
        logger.info(f"Fetching feed: {feed_cfg.name or feed_cfg.url}")
        try:
            # feedparser is synchronous, run in executor
            loop = asyncio.get_running_loop()
            feed_data = await loop.run_in_executor(None, feedparser.parse, feed_cfg.url)

            tasks = [
                process_and_save_article(entry, feed_cfg, client, app_config, session_factory)
                for entry in feed_data.entries
            ]
            await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Error processing feed {feed_cfg.url}: {e}")

        logger.info(f"Feed '{feed_cfg.name or feed_cfg.url}' cycle complete. Sleeping {feed_cfg.interval_seconds}s")
        await asyncio.sleep(feed_cfg.interval_seconds)
