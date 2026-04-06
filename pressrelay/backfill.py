import asyncio
import argparse
from datetime import datetime
from typing import List, Set

import yfinance as yf
from sqlalchemy import select
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from curl_cffi.requests import AsyncSession as AsyncSessionCffi

from pressrelay.logger import logger
from pressrelay.config import settings
from pressrelay.database import get_db_engine, get_session_factory, Watchlist, Article, ArticleStatus
from pressrelay.client import AsyncClientManager
from pressrelay.tasks import process_and_save_article

TRUSTED_PROVIDERS = {"GlobeNewswire", "BusinessWire", "PR Newswire", "PRNewswire"}

# Yahoo Finance specific rate limit error can manifest as various exceptions
try:
    from yfinance.exceptions import YFRateLimitError
except ImportError:
    class YFRateLimitError(Exception): pass

@retry(
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type((Exception,)),
    before_sleep=lambda retry_state: logger.warning(f"Rate limited or error. Retrying in {retry_state.next_action.sleep} seconds... (Attempt {retry_state.attempt_number})")
)
def fetch_news_with_retry(ticker_symbol: str):
    """Synchronous wrapper for yfinance news fetching with exponential backoff."""
    ticker = yf.Ticker(ticker_symbol)
    return ticker.get_news(tab="press releases")

async def backfill_ticker(
    ticker_symbol: str,
    start_date: datetime,
    app_config,
    session_factory,
    client: AsyncSessionCffi,
    dry_run: bool = False,
    watchlist_set: Set[str] = None
):
    """Backfills news for a specific ticker from Yahoo Finance."""
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Backfilling ticker: {ticker_symbol}")
    
    try:
        loop = asyncio.get_running_loop()
        news_items = await loop.run_in_executor(None, fetch_news_with_retry, ticker_symbol)
        
        if not news_items:
            logger.debug(f"No press releases found for {ticker_symbol}")
            return

        processed_count = 0
        for item in news_items:
            content = item.get("content", {})
            provider = content.get("provider", {}).get("displayName")
            
            if provider not in TRUSTED_PROVIDERS:
                continue
                
            pub_date_str = content.get("pubDate")
            if not pub_date_str:
                continue
                
            pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            
            if pub_date.replace(tzinfo=None) < start_date:
                continue

            article_url = content.get("clickThroughUrl", {}).get("url")
            if not article_url:
                continue

            mock_entry = {
                "link": article_url,
                "title": content.get("title", "No Title"),
                "published_parsed": pub_date.timetuple()
            }
            
            from pressrelay.config import FeedConfig
            mock_feed_cfg = FeedConfig(url=f"backfill://{provider}", name=provider)

            async with session_factory() as session:
                success = await process_and_save_article(
                    mock_entry,
                    mock_feed_cfg,
                    client,
                    app_config,
                    session,
                    None,
                    dry_run=dry_run,
                    primary_ticker=ticker_symbol,
                    watchlist_set=watchlist_set
                )
            if success:
                processed_count += 1
            
        if processed_count > 0:
            logger.success(f"{'[DRY RUN] Would have backfilled' if dry_run else 'Backfilled'} {processed_count} articles for {ticker_symbol}")

    except Exception as e:
        logger.error(f"Failed to backfill ticker {ticker_symbol} after retries: {e}")

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
    
    async with session_factory() as session:
        res = await session.execute(select(Watchlist.ticker).where(Watchlist.is_active == 1))
        active_tickers = set(res.scalars().all())
            
        if args.ticker:
            tickers_to_process = [args.ticker.upper()]
        else:
            tickers_to_process = list(active_tickers)

    logger.info(f"Starting {'[DRY RUN] ' if args.dry_run else ''}backfill from {args.start_date} for {len(tickers_to_process)} tickers.")
    
    client = AsyncClientManager.get_client()
    
    chunk_size = 3
    for i in range(0, len(tickers_to_process), chunk_size):
        chunk = tickers_to_process[i:i+chunk_size]
        tasks = [
            backfill_ticker(t, start_date, config, session_factory, client, dry_run=args.dry_run, watchlist_set=active_tickers)
            for t in chunk
        ]
        await asyncio.gather(*tasks)
        await asyncio.sleep(2)

    await AsyncClientManager.close_client()

if __name__ == "__main__":
    asyncio.run(main())
