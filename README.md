# PressRelay

A high-performance asynchronous service that monitors financial RSS feeds, extracts clean article content, tags relevant stock tickers, and stores them as structured Markdown for LLM/RAG consumption.

## Core Features

*   **V2 Architecture:** Fully asynchronous pipeline using `httpx`, `SQLAlchemy 2.0` (aiosqlite), and `uv`.
*   **Hashed Storage:** Articles are stored in a content-addressed directory structure (`data/storage/ab/cd/hash-slug.md`) for maximum filesystem efficiency.
*   **Ticker Detection:** High-speed keyword extraction using `FlashText` to tag 1,100+ healthcare stock symbols in every article.
*   **Smart Ingestion:** Supports `ETag` and `Last-Modified` headers to minimize bandwidth and skip unchanged feeds.
*   **Backfill Mode:** Integrated `yfinance` support to historically ingest press releases for specific tickers or the entire watchlist.
*   **Reliability:** Built-in feed health tracking, error logging, and a dedicated retry mechanism for failed articles.

## Quick Start

### 1. Installation
The project uses `uv` for dependency management.
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### 2. Setup Watchlist
Import the default healthcare tickers into the database:
```bash
uv run python -m pressrelay.importer
```

### 3. Run the Service
Start the continuous monitoring loop:
```bash
uv run -m pressrelay.main
```

## CLI Usage

### Continuous Monitoring
```bash
uv run -m pressrelay.main [--dry-run]
```

### Backfill Historical Data
Ingest Yahoo Finance press releases from trusted sources:
```bash
# Backfill everything since 2026-01-01
uv run python -m pressrelay.backfill

# Backfill a specific ticker since a specific date
uv run python -m pressrelay.backfill --ticker MDAI --start-date 2025-12-01
```

### Retry Failed Articles
Re-attempt processing for articles marked as `FAILED` in the database:
```bash
uv run python -m pressrelay.retry [--dry-run]
```

## Tech Stack

*   **Language:** Python 3.14+
*   **Package Manager:** `uv`
*   **Scraping:** `trafilatura`, `feedparser`, `yfinance`
*   **Conversion:** `html-to-markdown`
*   **Database:** `SQLAlchemy` (Async), `SQLite`
*   **Logic:** `Pydantic` (Settings), `FlashText` (Ticker detection)
