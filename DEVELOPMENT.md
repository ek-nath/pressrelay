# Development Guide

This document provides technical details and instructions for developers looking to contribute to or extend `pressrelay`.

## Quick Start

The project uses `uv` for lightning-fast dependency management and Python environment handling.

1.  **Install `uv`** (if not already installed):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Sync Environment:**
    ```bash
    uv sync
    ```
    This will automatically create a `.venv` with Python 3.14 and install all dependencies.

3.  **Run the Service:**
    ```bash
    uv run -m pressrelay.main
    ```

## Architecture Deep-Dive

`pressrelay` is designed as an asynchronous service to handle multiple RSS feeds and network requests concurrently.

### 1. Entry Point (`pressrelay/main.py`)
Initializes the database using `SQLAlchemy` (with `aiosqlite` for async support) and kicks off the main processing loop.

### 2. Task Orchestration (`pressrelay/tasks.py`)
Contains the logic for:
-   Fetching RSS feeds using `feedparser`.
-   Filtering out already processed articles by checking the database.
-   Managing the async concurrency for processing multiple articles.

### 3. Content Processing (`pressrelay/processing.py`)
The pipeline for a single URL:
1.  **Download:** Uses `httpx` to fetch the raw HTML.
2.  **Extraction:** Uses `trafilatura` to identify and extract the "boiler-plate free" main content.
3.  **Conversion:** Uses `html-to-markdown` to transform the cleaned HTML into structured Markdown.

### 4. Database (`pressrelay/database.py`)
Uses `SQLAlchemy`'s async extension. The schema is defined in the `Article` class. Metadata includes:
-   Original URL (Unique constraint to prevent duplicates).
-   Local Markdown path.
-   Source feed and publication dates.

## How to Extend

### Adding a New Feed
Modify `config.yml` in the project root:
```yaml
feeds:
  - url: "https://example.com/rss"
    interval_seconds: 600
```

### Changing the Markdown Logic
If you want to customize how Markdown is generated (e.g., stripping certain tags or changing header styles), modify the `convert()` call in `pressrelay/processing.py`.

### Database Migrations
Currently, the project uses `create_db_and_tables()` which creates tables if they don't exist. For production-grade schema changes, consider adding `alembic`.

## Testing
The project uses `pytest`. Run tests using:
```bash
uv run pytest
```

## Project Standards
-   **Logging:** Use `loguru`. Avoid `print()` statements in the core logic.
-   **Async:** All I/O bound operations (HTTP, DB, File System) MUST be `async`.
-   **Types:** Use Python type hints for all function signatures.
