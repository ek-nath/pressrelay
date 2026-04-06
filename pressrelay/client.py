import httpx
from typing import Optional
from pressrelay.logger import logger

class AsyncClientManager:
    _instance: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._instance is None:
            logger.debug("Initializing Global Singleton httpx.AsyncClient...")
            cls._instance = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Referer": "https://www.google.com/",
                    "DNT": "1"
                }
            )
        return cls._instance

    @classmethod
    async def close_client(cls):
        if cls._instance:
            logger.debug("Closing Global Singleton httpx.AsyncClient...")
            await cls._instance.aclose()
            cls._instance = None
