import asyncio
import argparse
from datetime import datetime
from typing import List

import yfinance as yf
from sqlalchemy import select

from pressrelay.logger import logger
from pressrelay.config import settings
from pressrelay.database import get_db_engine, get_session_factory, Watchlist, Article, ArticleStatus
from pressrelay.client import AsyncClientManager
from pressrelay.tasks import process_and_save_article, KeywordProcessor

TRUSTED_PROVIDERS = {"GlobeNewswire", "BusinessWire", "PR Newswire", "PRNewswire"}

async def backfill_ticker(
    ticker_symbol: str,
    start_date: datetime,
    app_config,
    session_factory,
    client,
    keyword_processor,
    dry_run: bool = False
):
    """Backfills news for a specific ticker from Yahoo Finance."""
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Backfilling ticker: {ticker_symbol}")
    
    try:
        # yfinance is synchronous, but we only call it once per ticker
        ticker = yf.Ticker(ticker_symbol)
        news_items = ticker.get_news(tab="press releases")
        
        if not news_items:
            logger.debug(f"No press releases found for {ticker_symbol}")
            return

        processed_count = 0
        for item in news_items:
            content = item.get("content", {})
            provider = content.get("provider", {}).get("displayName")
            
            # 1. Filter by Provider
            if provider not in TRUSTED_PROVIDERS:
                continue
                
            # 2. Filter by Date
            pub_date_str = content.get("pubDate")
            if not pub_date_str:
                continue
                
            # pub_date_str example: 2026-03-24T20:25:00Z
            pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            
            if pub_date.replace(tzinfo=None) < start_date:
                continue

            # 3. Prepare for saving
            article_url = content.get("clickThroughUrl", {}).get("url")
            if not article_url:
                continue

            # Transform into a format compatible with process_and_save_article (which expects feedparser entry)
            # We mock the entry dict
            mock_entry = {
                "link": article_url,
                "title": content.get("title", "No Title"),
                "published_parsed": pub_date.timetuple()
            }
            
            # Mock FeedConfig
            from pressrelay.config import FeedConfig
            mock_feed_cfg = FeedConfig(url=f"backfill://{provider}", name=provider)

            success = await process_and_save_article(
                mock_entry,
                mock_feed_cfg,
                client,
                app_config,
                session_factory,
                keyword_processor,
                dry_run=dry_run
            )
            if success:
                processed_count += 1
            
        if processed_count > 0:
            logger.success(f"{'[DRY RUN] Would have backfilled' if dry_run else 'Backfilled'} {processed_count} articles for {ticker_symbol}")

    except Exception as e:
        logger.error(f"Error backfilling ticker {ticker_symbol}: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Backfill historical news articles.")
    parser.add_argument("--start-date", type=str, default="2026-01-01", help="ISO date YYYY-MM-DD")
    parser.add_argument("--ticker", type=str, help="Specific ticker to backfill (optional)")
    parser.add_argument("--dry-run", action="store_true", help="Run without saving changes")
    args = parser.parse_args()

    start_date = datetime.fromisoformat(args.start_date)
    config = settings.load_config()
    engine = await get_db_engine(config.database_url)
    session_factory = get_session_factory(engine)
    
    # Initialize Ticker Detection
    keyword_processor = KeywordProcessor(case_sensitive=True)
    async with session_factory() as session:
        # Load all tickers for detection
        res = await session.execute(select(Watchlist.ticker).where(Watchlist.is_active == 1))
        all_tickers = res.scalars().all()
        for t in all_tickers:
            keyword_processor.add_keyword(t)
            
        # Determine which tickers to process
        if args.ticker:
            tickers_to_process = [args.ticker.upper()]
        else:
            tickers_to_process = all_tickers

    logger.info(f"Starting {'[DRY RUN] ' if args.dry_run else ''}backfill from {args.start_date} for {len(tickers_to_process)} tickers.")
    
    client = AsyncClientManager.get_client()
    
    # Process in chunks to avoid overwhelming system/network
    chunk_size = 5
    for i in range(0, len(tickers_to_process), chunk_size):
        chunk = tickers_to_process[i:i+chunk_size]
        tasks = [
            backfill_ticker(t, start_date, config, session_factory, client, keyword_processor, dry_run=args.dry_run)
            for t in chunk
        ]
        await asyncio.gather(*tasks)
        # Small sleep between chunks
        await asyncio.sleep(1)

    await AsyncClientManager.close_client()

if __name__ == "__main__":
    asyncio.run(main())
