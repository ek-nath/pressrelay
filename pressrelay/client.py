from typing import Optional
from curl_cffi.requests import AsyncSession
from pressrelay.logger import logger

class AsyncClientManager:
    _instance: Optional[AsyncSession] = None

    @classmethod
    def get_client(cls) -> AsyncSession:
        if cls._instance is None:
            logger.debug("Initializing Global Singleton curl-cffi AsyncSession (impersonating Chrome)...")
            # curl-cffi allows us to impersonate a real browser's TLS fingerprint
            cls._instance = AsyncSession(
                impersonate="chrome",
                timeout=30.0,
                follow_redirects=True,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                    "DNT": "1"
                }
            )
        return cls._instance

    @classmethod
    async def close_client(cls):
        if cls._instance:
            logger.debug("Closing Global Singleton curl-cffi AsyncSession...")
            # AsyncSession in curl-cffi doesn't have aclose(), it uses close() but it's not always needed
            # However, for consistency we'll clean up.
            cls._instance = None
