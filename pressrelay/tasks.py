import asyncio
import os
import re
import feedparser
from datetime import datetime
from time import mktime
import httpx
import aiofiles

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from pressrelay.logger import logger
from pressrelay.database import AsyncSessionLocal, Article
from pressrelay.processing import fetch_and_convert_to_markdown

def slugify(text: str) -> str:
    """Convert a string to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W-]+', '-', text)
    return text.strip('-')

async def process_and_save_article(
    entry: dict, feed_url: str, client: httpx.AsyncClient, markdown_dir: str
):
    """Processes a single article entry: fetches, converts, and saves."""
    article_url = entry.get('link')
    if not article_url:
        return

    async with AsyncSessionLocal() as session:
        # 1. Check if article already exists in the DB
        result = await session.execute(select(Article).filter_by(url=article_url))
        if result.scalars().first():
            return  # Skip if already processed

        logger.info(f"New article found: '{entry.title}'")

        # 2. Fetch and convert the article content
        markdown_content = await fetch_and_convert_to_markdown(article_url, client)
        if not markdown_content:
            return

        # 3. Determine published date
        published_date = datetime.utcnow()
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            published_date = datetime.fromtimestamp(mktime(entry.published_parsed))

        # 4. Save markdown file asynchronously
        date_path = published_date.strftime("%Y/%m")
        article_slug = slugify(entry.title)
        filename = f"{article_slug[:100]}.md"
        full_dir = os.path.join(markdown_dir, date_path)
        os.makedirs(full_dir, exist_ok=True)
        file_path = os.path.join(full_dir, filename)

        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(markdown_content)
        except IOError as e:
            logger.error(f"Error saving markdown file {file_path}: {e}")
            return

        # 5. Add new article to the database session and commit
        new_article = Article(
            title=entry.title,
            url=article_url,
            source_feed=feed_url,
            published_date=published_date,
            processed_date=datetime.utcnow(),
            markdown_path=file_path,
        )
        session.add(new_article)
        await session.commit()
        logger.success(f"Successfully saved article: {entry.title}")

async def feed_processing_loop(feed_config: dict, client: httpx.AsyncClient):
    """An infinite loop that periodically fetches and processes a single RSS feed."""
    feed_url = feed_config['url']
    interval = feed_config['interval_seconds']
    markdown_dir = load_config().get("markdown", {}).get("storage_path", "data/markdown")

    while True:
        logger.info(f"Fetching feed: {feed_url}")
        try:
            loop = asyncio.get_running_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            tasks = [
                process_and_save_article(entry, feed_url, client, markdown_dir)
                for entry in feed.entries
            ]
            await asyncio.gather(*tasks)

        except Exception as e:
            logger.error(f"Error processing feed {feed_url}: {e}", exc_info=True)

        logger.info(f"Feed '{feed_url}' processed. Sleeping for {interval} seconds.")
        await asyncio.sleep(interval)

# Helper to load config in this module as well
from pressrelay.database import load_config