import asyncio
import os
import re
import hashlib
import feedparser
from datetime import datetime
from time import mktime
from typing import Optional, Callable, List, Tuple, Dict, Any, Set
import httpx
import aiofiles
from flashtext import KeywordProcessor

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from pressrelay.logger import logger
from pressrelay.database import Article, ArticleStatus, Feed, Watchlist
from pressrelay.processing import fetch_and_convert_to_markdown
from pressrelay.config import AppConfig, FeedConfig
import time
from pressrelay.metrics import ARTICLES_PROCESSED, FEED_FETCH_TOTAL, PROCESSING_LATENCY, ACTIVE_TICKERS, TICKERS_DETECTED, FEED_ERROR_COUNT

def slugify(text: str) -> str:
    """Convert a string to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W-]+', '-', text)
    return text.strip('-')

def get_content_hash(content: str) -> str:
    """Generate a SHA256 hash of the content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def detect_tickers_deterministic(
    title: str, 
    content: str, 
    watchlist: Set[str]
) -> List[str]:
    """
    Highly deterministic ticker detection using PR industry patterns.
    """
    detected = set()
    
    # 1. Pattern: (EXCHANGE: TICKER) or (TICKER) in first 1000 chars
    # Matches: (Nasdaq: MDAI), (NASDAQ:MDAI), (NYSE: AEON), (SNDX)
    combined_text = f"{title} {content[:1000]}"
    paren_matches = re.findall(r'\((?:[A-Za-z\s]+: ?)?([A-Z]{1,5})\)', combined_text)
    for m in paren_matches:
        if m in watchlist:
            detected.add(m)
            
    # 2. Pattern: $TICKER
    dollar_matches = re.findall(r'\$([A-Z]{1,5})\b', content)
    for m in dollar_matches:
        if m in watchlist:
            detected.add(m)
            
    # 3. Pattern: EXCHANGE:TICKER (without parens)
    exchange_matches = re.findall(r'(?:NASDAQ|NYSE|OTC|TSX): ?([A-Z]{1,5})\b', combined_text, re.IGNORECASE)
    for m in exchange_matches:
        if m.upper() in watchlist:
            detected.add(m.upper())

    return list(detected)

async def process_and_save_article(
    entry: dict, 
    feed_cfg: FeedConfig, 
    client: httpx.AsyncClient, 
    app_config: AppConfig,
    session: AsyncSession,
    keyword_processor: Optional[KeywordProcessor] = None,
    dry_run: bool = False,
    primary_ticker: Optional[str] = None,
    watchlist_set: Optional[Set[str]] = None
) -> bool:
    """Processes a single article entry: fetches, converts, and saves with V2 logic."""
    start_time = time.time()
    article_url = entry.get('link')
    if not article_url:
        return False

    # 1. Check if article already exists in the DB
    stmt = select(Article).where(Article.url == article_url)
    result = await session.execute(stmt)
    existing_article = result.scalars().first()
    
    if existing_article and existing_article.status == ArticleStatus.SUCCESS:
        return True  # Already processed successfully

    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Processing article: '{entry.get('title', 'No Title')}'")

    # 2. Fetch and convert the article content
    markdown_content, metadata = await fetch_and_convert_to_markdown(article_url, client)
    
    if not markdown_content:
        if not dry_run:
            ARTICLES_PROCESSED.labels(status="failed", source=feed_cfg.name or "unknown").inc()
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
        return False

    # 3. Determine metadata, hashes, and tickers
    content_hash = get_content_hash(markdown_content)
    
    # New Deterministic Detection
    title = entry.get('title', '')
    if watchlist_set:
        detected_tickers = detect_tickers_deterministic(title, markdown_content, watchlist_set)
    else:
        detected_tickers = []
        
    if primary_ticker:
        detected_tickers.append(primary_ticker)
        
    # Dedup
    detected_tickers = list(set(detected_tickers))
        
    if metadata is None:
        metadata = {}
    metadata['detected_tickers'] = detected_tickers
    if primary_ticker:
        metadata['primary_ticker'] = primary_ticker

    if dry_run:
        logger.info(f"[DRY RUN] Would save article: {entry.get('title')} (Tickers: {', '.join(detected_tickers)})")
        return True

    published_at = datetime.utcnow()
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        published_at = datetime.fromtimestamp(mktime(entry.published_parsed))

    # 4. Save markdown file
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
        ARTICLES_PROCESSED.labels(status="failed", source=feed_cfg.name or "unknown").inc()
        return False

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
    
    # Record Success Metrics
    ARTICLES_PROCESSED.labels(status="success", source=feed_cfg.name or "unknown").inc()
    PROCESSING_LATENCY.observe(time.time() - start_time)
    for ticker in detected_tickers:
        TICKERS_DETECTED.labels(ticker=ticker).inc()

    if detected_tickers:
        logger.success(f"Successfully saved article: {entry.get('title')} (Tickers: {', '.join(detected_tickers)})")
    else:
        logger.success(f"Successfully saved article: {entry.get('title')}")
    return True

async def update_feed_health(
    feed_cfg: FeedConfig, 
    session_factory: Callable[[], AsyncSession],
    error: bool = False,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None
):
    """Updates the feeds table with the latest fetch status and efficiency headers."""
    FEED_FETCH_TOTAL.labels(feed_name=feed_cfg.name or feed_cfg.url, status="error" if error else "success").inc()
    
    async with session_factory() as session:
        stmt = select(Feed).where(Feed.url == feed_cfg.url)
        result = await session.execute(stmt)
        feed = result.scalars().first()
        
        if not feed:
            feed = Feed(url=feed_cfg.url, name=feed_cfg.name)
            session.add(feed)
        
        feed.last_fetch_at = datetime.utcnow()
        if error:
            feed.error_count = (feed.error_count or 0) + 1
        else:
            feed.error_count = 0 # Reset on success

            
        FEED_ERROR_COUNT.labels(feed_name=feed_cfg.name or feed_cfg.url).set(feed.error_count)

        if etag:
            feed.etag = etag
        if last_modified:
            feed.last_modified = last_modified
            
        await session.commit()

async def feed_processing_loop(
    feed_cfg: FeedConfig, 
    app_config: AppConfig,
    session_factory: Callable[[], AsyncSession],
    client: httpx.AsyncClient,
    dry_run: bool = False
):
    """Infinite loop for fetching and processing a single RSS feed."""
    
    # Limit concurrency to avoid DB pool overflow and network congestion
    semaphore = asyncio.BoundedSemaphore(10)

    # Initialize Watchlist Set for deterministic detection
    async with session_factory() as session:
        result = await session.execute(select(Watchlist.ticker).where(Watchlist.is_active == 1))
        active_tickers = set(result.scalars().all())
        ACTIVE_TICKERS.set(len(active_tickers))
    
    logger.info(f"Deterministic detection initialized with {len(active_tickers)} tickers for {feed_cfg.url}")
    
    while True:
        logger.info(f"Fetching feed: {feed_cfg.name or feed_cfg.url}")
        fetch_error = False
        etag = None
        last_modified = None
        
        if not dry_run:
            async with session_factory() as session:
                stmt = select(Feed).where(Feed.url == feed_cfg.url)
                res = await session.execute(stmt)
                db_feed = res.scalars().first()
                if db_feed:
                    etag = db_feed.etag
                    last_modified = db_feed.last_modified

        try:
            loop = asyncio.get_running_loop()
            feed_data = await loop.run_in_executor(
                None, 
                lambda: feedparser.parse(feed_cfg.url, etag=etag, modified=last_modified)
            )
            
            if getattr(feed_data, 'status', None) == 304:
                logger.info(f"Feed '{feed_cfg.name or feed_cfg.url}' unchanged (304 Not Modified).")
            else:
                async def sem_process(entry):
                    async with semaphore:
                        async with session_factory() as session:
                            return await process_and_save_article(
                                entry, feed_cfg, client, app_config, session, None, 
                                dry_run=dry_run, watchlist_set=active_tickers
                            )

                tasks = [sem_process(entry) for entry in feed_data.entries]
                await asyncio.gather(*tasks)

            if not dry_run:
                new_etag = getattr(feed_data, 'etag', None)
                new_modified = getattr(feed_data, 'modified', None)
                await update_feed_health(feed_cfg, session_factory, error=False, etag=new_etag, last_modified=new_modified)

        except Exception as e:
            logger.error(f"Error processing feed {feed_cfg.url}: {e}", exc_info=True)
            if not dry_run:
                await update_feed_health(feed_cfg, session_factory, error=True)

        logger.info(f"Feed '{feed_cfg.name or feed_cfg.url}' cycle complete. Sleeping {feed_cfg.interval_seconds}s")
        await asyncio.sleep(feed_cfg.interval_seconds)
