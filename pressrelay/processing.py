import asyncio
from typing import Union, Tuple, Dict, Any

import httpx
import trafilatura
from html_to_markdown import convert

from pressrelay.logger import logger

async def fetch_and_convert_to_markdown(
    url: str, 
    client: httpx.AsyncClient
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Fetches the main content from a URL asynchronously and converts it to Markdown.
    Returns: (markdown_content, metadata_dict)
    """
    logger.debug(f"Processing URL: {url}")
    try:
        logger.debug("Downloading content...")
        response = await client.get(url)
        response.raise_for_status()
        downloaded_html = response.text

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error {e.response.status_code} for URL: {e.request.url}")
        return None, None
    except httpx.RequestError as e:
        logger.warning(f"Network error for URL {e.request.url}: {e.__class__.__name__}")
        return None, None

    # 2. Extract main content
    logger.debug("Extracting main content...")
    main_content_html = trafilatura.extract(
        downloaded_html, 
        include_comments=False, 
        include_tables=True, 
        output_format="html"
    )
    if not main_content_html:
        logger.warning(f"Failed to extract main content from {url}")
        return None, None

    # 3. Convert to Markdown and Capture Metadata
    logger.debug("Converting HTML to Markdown...")
    try:
        result = convert(main_content_html)
        if isinstance(result, dict):
            markdown_content = result.get('content')
            metadata = result.get('metadata', {})
            # Add some trafilatura metadata if missing
            trafil_metadata = trafilatura.extract_metadata(downloaded_html)
            if trafil_metadata:
                metadata['trafilatura'] = {
                    "author": trafil_metadata.author,
                    "date": trafil_metadata.date,
                    "sitename": trafil_metadata.sitename,
                    "description": trafil_metadata.description
                }
            return markdown_content, metadata
        else:
            return str(result), {}
            
    except Exception as e:
        logger.error(f"Error converting HTML to Markdown for {url}: {e}")
        return None, None
