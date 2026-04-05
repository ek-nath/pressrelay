# Development Guide

This document provides technical details for developers looking to maintain or extend the `pressrelay` service.

## Core Architectural Patterns

### 1. Asynchronous Pipeline
The service is built on `asyncio`. All I/O operations (HTTP requests via `httpx`, Database queries via `aiosqlite`, and File I/O via `aiofiles`) are non-blocking. This allows the service to process multiple RSS feeds and articles concurrently.

### 2. Ticker Detection (High Performance)
Instead of using slow regular expressions for 1,100+ tickers, we use **FlashText**. 
- Tickers are loaded from the `watchlist` table into a `KeywordProcessor` singleton within each feed loop.
- Detection is $O(N)$ relative to the length of the article, regardless of the number of tickers in the watchlist.

### 3. Content-Addressed Hashed Storage
To prevent filesystem performance degradation and filename collisions:
- We generate a SHA256 hash of the cleaned Markdown content.
- Files are stored at `data/storage/{hash[0:2]}/{hash[2:4]}/{hash[0:10]}-{slug}.md`.
- This ensures a balanced directory tree and easy deduplication.

### 4. HTTP Efficiency
The `feeds` table tracks `etag` and `last_modified` headers.
- `feedparser` sends these headers in subsequent requests.
- If the server returns a `304 Not Modified`, we skip the entire parsing and processing cycle for that feed.

## Database Schema (V2)

- **`feeds`**: Tracks RSS sources, health (error counts), and efficiency headers.
- **`watchlist`**: Stores the stock symbols to be detected in articles.
- **`articles`**: Stores metadata, content hashes, detected tickers (in `metadata_json`), and the local storage path.

## Key Modules

- **`pressrelay/main.py`**: Service entry point and loop orchestrator.
- **`pressrelay/tasks.py`**: The "workhorse" containing ingestion, extraction, and saving logic.
- **`pressrelay/backfill.py`**: logic for historical ingestion via Yahoo Finance.
- **`pressrelay/retry.py`**: Targeted re-processing of failed articles.
- **`pressrelay/importer.py`**: Utility to seed the watchlist.
- **`pressrelay/client.py`**: Singleton `httpx.AsyncClient` manager.

## Adding New Features

### Custom Metadata Extraction
If you need to extract more fields (e.g., social media counts or specific PR contact info), modify `pressrelay/processing.py`. The `metadata_json` column in the database is a flexible JSON field designed to store these extras without schema changes.

### New Storage Backends
The storage logic is currently in `tasks.py`. If moving to S3, you should abstract the `aiofiles` logic into a dedicated storage provider module.

## Testing
Run the test suite (requires pytest):
```bash
uv run pytest
```
*Note: Ensure you run with `--dry-run` when testing the main service to avoid polluting the local database.*
