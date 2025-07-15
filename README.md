# CFScraper API

A comprehensive scraper API service with FastAPI, SeleniumBase, and Cloudscraper for bypassing Cloudflare's anti-bot protection.

## Features

- **FastAPI-based REST API** with async support
- **Multiple scraper backends**:
  - CloudScraper for Cloudflare bypass
  - SeleniumBase for JavaScript-heavy sites
- **Job queue system** with Redis and in-memory options
- **Background job processing** with status tracking
- **Database integration** with SQLAlchemy
- **Health checks and monitoring**

## Installation

This project uses `uv` for dependency management. To get started:

```bash
# Install dependencies
uv sync

# Install development dependencies
uv sync --extra dev
```

## Usage

### Starting the Server

```bash
# Development server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### API Endpoints

#### Health Check
```bash
GET /health
```

#### Create Scraping Job
```bash
POST /api/v1/scrape
Content-Type: application/json

{
  "url": "https://example.com",
  "scraper_type": "cloudscraper",
  "method": "GET",
  "headers": {},
  "timeout": 30
}
```

#### Get Job Status
```bash
GET /api/v1/jobs/{task_id}
```

#### List Jobs
```bash
GET /api/v1/jobs?status=completed&limit=10
```

#### Queue Status
```bash
GET /api/v1/queue/status
```

### Demo Script

Run the demo script to see the API in action:

```bash
# Start the server first
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal, run the demo
uv run python demo.py
```

## Configuration

Environment variables can be set in a `.env` file:

```env
DATABASE_URL=sqlite:///./cfscraper.db
REDIS_URL=redis://localhost:6379
MAX_CONCURRENT_JOBS=10
JOB_TIMEOUT=300
USE_IN_MEMORY_QUEUE=true
```

## Architecture

### Core Components

1. **FastAPI Application** (`app/main.py`)
   - REST API with async support
   - Health checks and monitoring
   - Automatic database initialization

2. **Scraper Classes** (`app/scrapers/`)
   - Base scraper interface
   - CloudScraper implementation
   - SeleniumBase implementation
   - Factory pattern for scraper creation

3. **Job Queue System** (`app/utils/queue.py`)
   - Abstract queue interface
   - In-memory queue for development
   - Redis queue for production
   - Job status tracking

4. **Database Models** (`app/models/`)
   - SQLAlchemy models for jobs and results
   - Job status tracking
   - Result storage

5. **Background Processing** (`app/utils/executor.py`)
   - Async job execution
   - Concurrent job handling
   - Error handling and retries

## Testing

Run the test suite:

```bash
uv run pytest tests/ -v
```

## Development

### Project Structure

```
cfscraper/
├── alembic/           # Database migration scripts
├── app/
│   ├── api/           # API routes
│   ├── core/          # Core configuration
│   ├── models/        # Database models
│   ├── scrapers/      # Scraper implementations
│   ├── utils/         # Utilities (queue, executor)
│   └── main.py        # FastAPI application
├── docs/              # Documentation
├── examples/          # Demo scripts
├── tests/             # Test files
├── pyproject.toml     # Project configuration
└── README.md          # This file
```

### Adding New Scrapers

1. Create a new scraper class inheriting from `BaseScraper`
2. Implement the required methods
3. Register it in the `ScraperFactory`
4. Add it to the `ScraperType` enum

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.
