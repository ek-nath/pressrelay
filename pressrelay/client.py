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
                headers={"User-Agent": "PressRelay/2.0 (+https://github.com/ek-nath/pressrelay)"}
            )
        return cls._instance

    @classmethod
    async def close_client(cls):
        if cls._instance:
            logger.debug("Closing Global Singleton httpx.AsyncClient...")
            await cls._instance.aclose()
            cls._instance = None
