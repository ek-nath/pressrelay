import asyncio
import os
import re
import hashlib
import feedparser
from datetime import datetime
from time import mktime
from typing import Optional, Callable, List
import httpx
import aiofiles
from flashtext import KeywordProcessor

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pressrelay.logger import logger
from pressrelay.database import Article, ArticleStatus, Feed, Watchlist
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
    session_factory: Callable[[], AsyncSession],
    keyword_processor: Optional[KeywordProcessor] = None
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

        # 3. Determine metadata, hashes, and tickers
        content_hash = get_content_hash(markdown_content)
        
        # Detect tickers
        detected_tickers = []
        if keyword_processor and markdown_content:
            detected_tickers = keyword_processor.extract_keywords(markdown_content)
            # Dedup
            detected_tickers = list(set(detected_tickers))
            
        if metadata is None:
            metadata = {}
        metadata['detected_tickers'] = detected_tickers

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
            existing_article.metadata_json = metadata
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
                metadata_json=metadata
            )
            session.add(new_article)
            
        await session.commit()
        if detected_tickers:
            logger.success(f"Successfully saved article: {entry.get('title')} (Tickers: {', '.join(detected_tickers)})")
        else:
            logger.success(f"Successfully saved article: {entry.get('title')}")

async def update_feed_health(
    feed_cfg: FeedConfig, 
    session_factory: Callable[[], AsyncSession],
    error: bool = False,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None
):
    """Updates the feeds table with the latest fetch status and efficiency headers."""
    async with session_factory() as session:
        # Check if feed exists, if not create it
        stmt = select(Feed).where(Feed.url == feed_cfg.url)
        result = await session.execute(stmt)
        feed = result.scalars().first()
        
        if not feed:
            feed = Feed(url=feed_cfg.url, name=feed_cfg.name)
            session.add(feed)
        
        feed.last_fetch_at = datetime.utcnow()
        if error:
            feed.error_count += 1
        else:
            feed.error_count = 0 # Reset on success
            
        if etag:
            feed.etag = etag
        if last_modified:
            feed.last_modified = last_modified
            
        await session.commit()

async def feed_processing_loop(
    feed_cfg: FeedConfig, 
    app_config: AppConfig,
    session_factory: Callable[[], AsyncSession],
    client: httpx.AsyncClient
):
    """Infinite loop for fetching and processing a single RSS feed."""
    
    # Initialize KeywordProcessor for ticker detection
    keyword_processor = KeywordProcessor()
    async with session_factory() as session:
        result = await session.execute(select(Watchlist.ticker).where(Watchlist.is_active == 1))
        active_tickers = result.scalars().all()
        for ticker in active_tickers:
            keyword_processor.add_keyword(ticker)
    
    logger.info(f"Ticker detection initialized with {len(active_tickers)} tickers for {feed_cfg.url}")
    
    while True:
        logger.info(f"Fetching feed: {feed_cfg.name or feed_cfg.url}")
        fetch_error = False
        etag = None
        last_modified = None
        
        # Get existing headers from DB
        async with session_factory() as session:
            stmt = select(Feed).where(Feed.url == feed_cfg.url)
            res = await session.execute(stmt)
            db_feed = res.scalars().first()
            if db_feed:
                etag = db_feed.etag
                last_modified = db_feed.last_modified

        try:
            # feedparser is synchronous, run in executor
            loop = asyncio.get_running_loop()
            
            # feedparser supports etag and modified parameters
            feed_data = await loop.run_in_executor(
                None, 
                lambda: feedparser.parse(feed_cfg.url, etag=etag, modified=last_modified)
            )
            
            logger.debug(f"Feed {feed_cfg.url} response status: {getattr(feed_data, 'status', 'N/A')}, etag: {getattr(feed_data, 'etag', 'N/A')}, modified: {getattr(feed_data, 'modified', 'N/A')}")

            if feed_data.status == 304:
                logger.info(f"Feed '{feed_cfg.name or feed_cfg.url}' unchanged (304 Not Modified).")
            else:
                tasks = [
                    process_and_save_article(entry, feed_cfg, client, app_config, session_factory, keyword_processor)
                    for entry in feed_data.entries
                ]
                await asyncio.gather(*tasks)

            # Update health status and headers
            new_etag = getattr(feed_data, 'etag', None)
            new_modified = getattr(feed_data, 'modified', None)
            await update_feed_health(feed_cfg, session_factory, error=False, etag=new_etag, last_modified=new_modified)

        except Exception as e:
            logger.error(f"Error processing feed {feed_cfg.url}: {e}")
            await update_feed_health(feed_cfg, session_factory, error=True)

        logger.info(f"Feed '{feed_cfg.name or feed_cfg.url}' cycle complete. Sleeping {feed_cfg.interval_seconds}s")
        await asyncio.sleep(feed_cfg.interval_seconds)
