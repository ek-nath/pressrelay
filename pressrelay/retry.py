import asyncio
import argparse
from sqlalchemy import select
from pressrelay.database import get_db_engine, get_session_factory, Article, ArticleStatus, Watchlist
from pressrelay.config import settings, FeedConfig
from pressrelay.logger import logger
from pressrelay.client import AsyncClientManager
from pressrelay.tasks import process_and_save_article

async def retry_failed_articles(dry_run: bool = False):
    config = settings.load_config()
    engine = await get_db_engine(config.database_url)
    session_factory = get_session_factory(engine)
    
    # 1. Initialize Watchlist
    async with session_factory() as session:
        res = await session.execute(select(Watchlist.ticker).where(Watchlist.is_active == 1))
        active_tickers = set(res.scalars().all())

    # 2. Get Failed Articles
    async with session_factory() as session:
        stmt = select(Article).where(Article.status == ArticleStatus.FAILED)
        result = await session.execute(stmt)
        failed_articles = result.scalars().all()
        
        if not failed_articles:
            logger.info("No failed articles found to retry.")
            return

        logger.info(f"Found {len(failed_articles)} failed articles. Starting retry...")
        
        client = AsyncClientManager.get_client()
        success_count = 0
        
        for art in failed_articles:
            mock_entry = {
                "link": art.url,
                "title": art.title,
                "published_parsed": art.published_at.timetuple() if art.published_at else None
            }
            mock_feed_cfg = FeedConfig(url=art.source_feed, name="Retry")
            
            success = await process_and_save_article(
                mock_entry,
                mock_feed_cfg,
                client,
                config,
                session_factory,
                None,
                dry_run=dry_run,
                watchlist_set=active_tickers
            )
            if success:
                success_count += 1
                
        logger.success(f"Retry complete. Successfully processed {success_count}/{len(failed_articles)} articles.")
        await AsyncClientManager.close_client()

async def main():
    parser = argparse.ArgumentParser(description="Retry failed article processing")
    parser.add_argument("--dry-run", action="store_true", help="Run without saving changes")
    args = parser.parse_args()
    
    await retry_failed_articles(dry_run=args.dry_run)

if __name__ == "__main__":
    asyncio.run(main())
