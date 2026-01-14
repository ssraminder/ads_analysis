# Google Ads Competitive Intelligence Crawler

A comprehensive web scraping system to discover businesses advertising on Google for specific keywords and analyze their advertising strategies.

## Features

- **Keyword Scraping**: Scrape Google SERP for ads on specific keywords
- **Advertiser Discovery**: Track which domains are advertising and on which keywords
- **Keyword Expansion**: Automatically discover more keywords advertisers bid on
- **Spend Estimation**: Estimate advertising spend based on position and frequency data
- **Competitor Analysis**: Find and compare competing advertisers
- **REST API**: Full REST API for managing keywords, advertisers, and jobs
- **Async Processing**: Celery-based task queue for background processing
- **Proxy Support**: Built-in support for Bright Data, Oxylabs, and custom proxies
- **Anti-Detection**: Stealth measures to avoid blocking

## Tech Stack

- **Language**: Python 3.11+
- **Web Scraping**: Playwright (async)
- **Task Queue**: Celery with Redis
- **Database**: PostgreSQL with SQLAlchemy ORM
- **API**: FastAPI
- **Containerization**: Docker + Docker Compose

## Quick Start

### Using Docker Compose (Recommended)

1. Clone the repository and navigate to the project:
```bash
cd google-ads-crawler
```

2. Copy the example environment file:
```bash
cp .env.example .env
```

3. Start all services:
```bash
docker-compose up -d
```

4. The API will be available at `http://localhost:8000`
   - API Documentation: `http://localhost:8000/docs`
   - Health Check: `http://localhost:8000/health`

### Local Development

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your database and Redis URLs
```

4. Run database migrations:
```bash
alembic upgrade head
```

5. Start the API:
```bash
uvicorn src.api.main:app --reload
```

6. Start Celery worker (in another terminal):
```bash
celery -A src.tasks.celery_app worker --loglevel=info
```

7. Start Celery beat scheduler (in another terminal):
```bash
celery -A src.tasks.celery_app beat --loglevel=info
```

## Usage

### Adding Seed Keywords

```bash
# Using the CLI script
python scripts/seed_keywords.py --categories saas ecommerce

# Or via API
curl -X POST http://localhost:8000/api/keywords/bulk \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["buy shoes online", "best running shoes"], "category": "ecommerce"}'
```

### Triggering a Scrape

```bash
# Scrape a specific keyword
curl -X POST http://localhost:8000/api/keywords/1/scrape \
  -H "Content-Type: application/json" \
  -d '{"geo": "US", "device": "desktop"}'

# Bulk scrape multiple keywords
curl -X POST http://localhost:8000/api/jobs/bulk-scrape \
  -H "Content-Type: application/json" \
  -d '{"keyword_ids": [1, 2, 3], "geo": "US"}'
```

### Viewing Results

```bash
# List all advertisers
curl http://localhost:8000/api/advertisers

# Get advertiser details
curl http://localhost:8000/api/advertisers/1

# Get keywords an advertiser appears on
curl http://localhost:8000/api/advertisers/1/keywords

# Get competitors
curl http://localhost:8000/api/advertisers/1/competitors
```

### Keyword Expansion

```bash
# Expand keywords for an advertiser
python scripts/run_expansion.py expand shoestore.com

# Find competitor keywords
python scripts/run_expansion.py competitors shoestore.com
```

## API Endpoints

### Keywords
- `POST /api/keywords` - Add a new keyword
- `POST /api/keywords/bulk` - Bulk add keywords
- `GET /api/keywords` - List all keywords
- `GET /api/keywords/{id}` - Get keyword details
- `GET /api/keywords/{id}/advertisers` - List advertisers on keyword
- `POST /api/keywords/{id}/scrape` - Trigger immediate scrape

### Advertisers
- `GET /api/advertisers` - List all advertisers
- `GET /api/advertisers/search?domain=` - Search by domain
- `GET /api/advertisers/{id}` - Get advertiser details
- `GET /api/advertisers/{id}/keywords` - Get advertiser's keywords
- `GET /api/advertisers/{id}/ads` - Get ad variations
- `GET /api/advertisers/{id}/competitors` - Get competitors
- `POST /api/advertisers/{id}/expand` - Trigger keyword expansion

### Jobs
- `GET /api/jobs` - List crawl jobs
- `GET /api/jobs/stats` - Get job statistics
- `GET /api/jobs/{id}` - Get job details
- `POST /api/jobs/bulk-scrape` - Queue bulk scraping

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection URL | Required |
| `REDIS_URL` | Redis connection URL | Required |
| `BRIGHTDATA_API_KEY` | Bright Data API key | Optional |
| `OXYLABS_USERNAME` | Oxylabs username | Optional |
| `SCRAPE_DELAY_MIN_SECONDS` | Min delay between scrapes | 30 |
| `SCRAPE_DELAY_MAX_SECONDS` | Max delay between scrapes | 120 |
| `MAX_REQUESTS_PER_PROXY_PER_HOUR` | Rate limit per proxy | 30 |
| `MAX_CONCURRENT_SCRAPERS` | Max concurrent scrape tasks | 5 |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   FastAPI   │────▶│   Celery    │────▶│  Playwright │
│    REST     │     │   Workers   │     │   Scraper   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ PostgreSQL  │     │    Redis    │     │   Proxies   │
│  Database   │     │   Broker    │     │  (Rotating) │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Important Notes

1. **Rate Limiting**: Google aggressively blocks scrapers. Start with conservative rate limits (1 request per 2 minutes per IP).

2. **Proxy Costs**: Residential proxies cost $10-15/GB. Optimize by caching results.

3. **Selector Changes**: Google frequently updates their HTML. The extractor has fallback selectors, but may need updates.

4. **Legal Considerations**: This tool is for educational purposes. Review Google's ToS before use.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src

# Run specific test file
pytest tests/test_expansion.py
```

## License

MIT License - See LICENSE file for details.
