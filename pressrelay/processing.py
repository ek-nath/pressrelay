import asyncio
from typing import Optional, Tuple, Dict, Any

from curl_cffi.requests import AsyncSession
import trafilatura
from lxml import etree
from html_to_markdown import convert

from pressrelay.logger import logger


def _extract_and_convert(downloaded_html: str, url: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Synchronously extracts main content + metadata in one pass and converts to Markdown."""
    doc = trafilatura.bare_extraction(
        downloaded_html,
        with_metadata=True,
        include_comments=False,
        include_tables=True,
    )
    if not doc or doc.body is None:
        logger.warning(f"Failed to extract main content from {url}")
        return None, None

    main_content_html = etree.tostring(doc.body, encoding="unicode")
    if not main_content_html:
        logger.warning(f"Failed to serialize main content from {url}")
        return None, None

    try:
        result = convert(main_content_html)
        if isinstance(result, dict):
            markdown_content = result.get('content')
            metadata = result.get('metadata', {})
            metadata['trafilatura'] = {
                "author": doc.author,
                "date": doc.date,
                "sitename": doc.sitename,
                "description": doc.description,
            }
            return markdown_content, metadata
        return str(result), {}
    except Exception as e:
        logger.error(f"Error converting HTML to Markdown for {url}: {e}")
        return None, None


async def fetch_and_convert_to_markdown(
    url: str,
    client: AsyncSession
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Fetches the main content from a URL asynchronously and converts it to Markdown.
    Uses curl-cffi for browser impersonation to bypass bot detection.
    """
    logger.debug(f"Processing URL: {url}")
    try:
        logger.debug("Downloading content...")
        response = await client.get(url)
        response.raise_for_status()
        downloaded_html = response.text

    except Exception as e:
        logger.warning(f"Fetch error for URL {url}: {e}")
        return None, None

    logger.debug("Extracting main content and converting HTML to Markdown...")
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extract_and_convert, downloaded_html, url)
