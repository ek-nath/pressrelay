# AGENTS.md

Guidance for coding agents and developers working in `/Users/ek/Projects/pressrelay`. For installation, CLI usage, and a high-level overview, see [README.md](README.md).

## Purpose

PressRelay is a news collection and extraction service for healthcare/biotech press releases. It supports historical dataset collection (via Yahoo Finance backfill) and live RSS feed polling with webhook triggering (`webhook_urls`) for downstream stock-price correlation and classification.

## Environment & Tooling

- **Python & Dependencies:** Python `>=3.14` managed with `uv` (`pyproject.toml`, `uv.lock`).
- **Running commands:** Use `.venv/bin/python` or `uv run` (for example, `.venv/bin/python -m pressrelay.main --dry-run` or `uv run pytest`).
- **Configuration:** `config.yml` (loaded by `pressrelay/config.py` via `Settings`, overridable with `PRESSRELAY_CONFIG_PATH`).

## Architecture & Entry Points

- **`pressrelay/main.py`**: Live RSS feed poller. Loads `config.yml` (`feeds`), initializes the DB and `AsyncClientManager` (`pressrelay/client.py`, wrapping `curl_cffi.requests.AsyncSession` with Chrome TLS impersonation), starts Prometheus metrics (`--metrics-port`, default `8000`), and runs `feed_processing_loop()` per feed using `feedparser` (sending `etag` / `last_modified` headers and skipping on `304 Not Modified`). Supports `--dry-run`.
- **`pressrelay/backfill.py`**: Historical press-release backfill using `yfinance.Ticker(ticker).get_news(tab="press releases")`, filtered to `TRUSTED_PROVIDERS` (`GlobeNewswire`, `BusinessWire`, `PR Newswire`, `PRNewswire`). Supports `--start-date` (default `2026-01-01`), `--ticker`, and `--dry-run`.
- **`pressrelay/tasks.py`**: Shared `process_and_save_article()` ingestion pipeline:
  - Deterministic ticker detection via `detect_tickers_deterministic()` (matching parenthesized, `$TICKER`, and exchange-prefixed patterns against the ticker set from `get_ticker_universe()` in `pressrelay/universe.py`).
  - Content hashing, markdown persistence, SQLite `Article` persistence, and async POST dispatch to `app_config.webhook_urls` via `send_webhooks()`.
- **`pressrelay/processing.py`**: `fetch_and_convert_to_markdown()` fetches HTML via `curl_cffi` `AsyncSession` and offloads single-pass `trafilatura.bare_extraction()` + `html_to_markdown.convert()` to the default executor via `loop.run_in_executor()`.
- **`pressrelay/retry.py`**: `retry_failed_articles()` queries `Article` rows with `ArticleStatus.FAILED` and re-runs `process_and_save_article()`. Supports `--dry-run`.
- **`pressrelay/importer.py`**: Utility to seed the `watchlist` table.
- **`pressrelay/database.py`**: SQLAlchemy async models (`Feed`, `Watchlist`, `Article`, `ArticleStatus`) and engine/session helpers.

## Storage & Content Format

- **SQLite database (`data/pressrelay_v2.db`, configured via `database_url` in `config.yml`):**
  - `feeds`: RSS source URLs, names, `last_fetch_at`, `error_count`, and conditional-GET headers (`etag`, `last_modified`).
  - `watchlist`: Stock symbols (`ticker`, `name`, `is_active`).
  - `articles`: `id`, `url`, `title`, `source_feed` (RSS URL or `backfill://<Provider>`), `status` (`SUCCESS` / `FAILED`), `content_hash` (SHA-256 hex digest of the markdown), `published_at`, `processed_at`, `markdown_path`, `metadata_json`, and `feed_id`.
  - `metadata_json`: Extensible JSON blob storing `detected_tickers`, optional `primary_ticker`, `trafilatura` metadata (`author`, `date`, `sitename`, `description`), and `html_to_markdown` document metadata (`document`, `headers`, `links`, `images`, `structured_data`).
- **Markdown files (`data/storage/{hash[0:2]}/{hash[2:4]}/{hash[:10]}-{slug}.md`):**
  - UTF-8 plain Markdown converted from the `trafilatura.bare_extraction()` HTML body via `html_to_markdown.convert()` (no YAML frontmatter; `slug` is the lowercased, hyphenated title truncated to 80 chars).

## Critical Data Invariants

- **UTC-only timestamps:** `articles.published_at` and `articles.processed_at` in `data/pressrelay_v2.db` MUST be stored as naive **UTC** `datetime` objects (for example, `datetime.utcnow()` and `datetime(*published_parsed[:6])` from UTC `struct_time`—never `time.mktime()`, which interprets tuples in local time). `process_and_save_article()` reads `entry.get('published_parsed')` so both `feedparser` `FeedParserDict` entries and plain `dict` entries (`backfill.py`, `retry.py`) work uniformly.
- **Deduplication:** Articles are deduplicated by both `Article.url` and `Article.content_hash` (SHA-256 of the converted markdown). When a duplicate is encountered, `_merge_detected_tickers()` merges any new `detected_tickers` into `metadata_json` without creating duplicate `Article` rows, markdown files, or webhook dispatches.
- **Testing Safety:** Never commit or mutate `data/pressrelay_v2.db` during tests—always use `--dry-run` or an in-memory SQLite URL (`sqlite+aiosqlite:///:memory:`).
