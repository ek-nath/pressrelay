from prometheus_client import Counter, Gauge, Histogram, Summary, start_http_server
from pressrelay.logger import logger

# 1. Define Metrics
ARTICLES_PROCESSED = Counter(
    "pressrelay_articles_processed_total", 
    "Total number of articles processed", 
    ["status", "source"]
)

FEED_FETCH_TOTAL = Counter(
    "pressrelay_feed_fetch_total", 
    "Total number of feed fetch attempts", 
    ["feed_name", "status"]
)

PROCESSING_LATENCY = Histogram(
    "pressrelay_article_processing_seconds", 
    "Time spent processing a single article",
    buckets=(1, 2, 5, 10, 30, 60)
)

ACTIVE_TICKERS = Gauge(
    "pressrelay_watchlist_tickers_total", 
    "Number of active tickers in the watchlist"
)

TICKERS_DETECTED = Counter(
    "pressrelay_tickers_detected_total", 
    "Total number of ticker mentions detected", 
    ["ticker"]
)

FEED_ERROR_COUNT = Gauge(
    "pressrelay_feed_errors", 
    "Current error count for a specific feed", 
    ["feed_name"]
)

def start_metrics_server(port: int = 8000):
    """Starts the Prometheus metrics exporter server."""
    logger.info(f"Starting Prometheus metrics server on port {port}...")
    start_http_server(port)
