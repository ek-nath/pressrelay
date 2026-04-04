import sys
from loguru import logger

# Remove default handler
logger.remove()

# Configure a new handler to stderr with a specific format and INFO level
logger.add(
    sys.stderr, 
    level="DEBUG",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# You could also add a file logger like this:
# logger.add("logs/app.log", rotation="10 MB", level="DEBUG")
