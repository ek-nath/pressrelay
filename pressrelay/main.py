import asyncio
import os
from pathlib import Path

import argparse
from pressrelay.logger import logger
from pressrelay.config import settings
from pressrelay.database import get_db_engine, create_db_and_tables, get_session_factory
from pressrelay.tasks import feed_processing_loop
from pressrelay.client import AsyncClientManager

async def main():
    """
    The main entry point for the new pressrelay architecture.
    """
    parser = argparse.ArgumentParser(description="PressRelay Service")
    parser.add_argument("--dry-run", action="store_true", help="Process feeds without saving to disk or DB")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE ENABLED. No changes will be persisted.")

    logger.info("Starting PressRelay Architecture V2...")
    
    # 1. Load Configuration
    try:
        config = settings.load_config()
        logger.info(f"Configuration loaded. DB: {config.database_url}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return

    # 2. Ensure Storage Exists
    if not args.dry_run:
        config.storage_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensuring storage path: {config.storage_path}")

    # 3. Initialize Database
    try:
        engine = await get_db_engine(config.database_url)
        if not args.dry_run:
            await create_db_and_tables(engine)
            logger.info("Database initialized with V2 Schema.")
        
        # Session factory for tasks
        session_factory = get_session_factory(engine)
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    # 4. Start Feed Processing
    logger.info(f"Starting processing for {len(config.feeds)} feeds...")
    
    client = AsyncClientManager.get_client()
    
    try:
        tasks = []
        for feed_cfg in config.feeds:
            tasks.append(feed_processing_loop(feed_cfg, config, session_factory, client, dry_run=args.dry_run))

        await asyncio.gather(*tasks)
    finally:
        await AsyncClientManager.close_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Service stopped by user.")
