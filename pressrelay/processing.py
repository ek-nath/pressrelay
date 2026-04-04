import asyncio
from typing import Union

import httpx
import trafilatura
from html_to_markdown import convert

from pressrelay.logger import logger


async def fetch_and_convert_to_markdown(url: str, client: httpx.AsyncClient) -> Union[str, None]:
    """
    Fetches the main content from a URL asynchronously and converts it to Markdown.

    Args:
        url: The URL of the article to process.
        client: An httpx.AsyncClient instance for making the request.

    Returns:
        The article content as a Markdown string, or None if processing fails.
    """
    logger.debug(f"Processing URL: {url}")
    try:
        # 1. Asynchronously download content using httpx
        logger.debug("Downloading content...")
        response = await client.get(url, follow_redirects=True, timeout=20.0)
        response.raise_for_status()  # Raise an exception for 4xx/5xx status codes
        downloaded_html = response.text

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} for URL: {e.request.url}")
        return None
    except httpx.RequestError as e:
        logger.warning(f"Network error for URL {e.request.url}: {e.__class__.__name__}")
        return None

    # 2. Extract main content (CPU-bound, run directly)
    logger.debug("Extracting main content...")
    main_content_html = trafilatura.extract(
        downloaded_html, include_comments=False, include_tables=True, output_format="html"
    )
    if not main_content_html:
        logger.warning(f"Failed to extract main content from {url}")
        return None

    # 3. Convert to Markdown (CPU-bound, run directly)
    logger.debug("Converting HTML to Markdown...")
    try:
        result = convert(main_content_html)
        # html-to-markdown returns a dict with 'content' and other metadata
        if isinstance(result, dict) and 'content' in result:
            markdown_content = result['content']
        else:
            markdown_content = str(result)
            
        logger.debug(f"Successfully processed URL: {url}")
        return markdown_content
    except Exception as e:
        logger.error(f"Error converting HTML to Markdown for {url}: {e}")
        return None


async def main_test():
    """For testing the script directly."""
    test_url = "https://www.globenewswire.com/news-release/2025/10/13/2959516/0/en/The-New-Era-of-AI-in-Healthcare-A-Comprehensive-Analysis.html"
    logger.info(f"Fetching and converting test URL: {test_url}")
    async with httpx.AsyncClient() as client:
        markdown = await fetch_and_convert_to_markdown(test_url, client)

    if markdown:
        logger.success("Successfully converted to Markdown (first 500 chars):")
        print("-" * 80)
        print(markdown[:500] + "...")
    else:
        logger.error("Failed to process the article.")


if __name__ == "__main__":
    asyncio.run(main_test())