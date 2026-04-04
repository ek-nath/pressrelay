import asyncio
import httpx

from pressrelay.logger import logger
from pressrelay.database import create_db_and_tables, load_config
from pressrelay.tasks import feed_processing_loop

async def main():
    """
    The main entry point for the application.
    Initializes the database and starts a concurrent processing loop for each feed.
    """
    logger.info("Initializing database...")
    await create_db_and_tables()
    logger.info("Database initialized.")

    config = load_config()
    feeds = config.get("feeds", [])

    async with httpx.AsyncClient() as client:
        # Create a concurrent task for each feed's processing loop
        feed_tasks = [
            feed_processing_loop(feed_config, client)
            for feed_config in feeds
        ]
        
        if not feed_tasks:
            logger.warning("No feeds found in config.yml. Exiting.")
            return

        logger.info(f"Starting processing for {len(feed_tasks)} feeds...")
        await asyncio.gather(*feed_tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")