# Railway Deployment Guide

## Services Required

You need to create 4 services in Railway:

### 1. PostgreSQL Database
- Add from Railway's database templates
- Copy the `DATABASE_URL` from the connection settings

### 2. Redis
- Add from Railway's database templates
- Copy the `REDIS_URL` from the connection settings

### 3. API Service (from this repo)
- Set start command: `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
- Add environment variables (see below)

### 4. Worker Service (from this repo)
- Set start command: `celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2`
- Add environment variables (see below)

## Environment Variables

Set these for both API and Worker services:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
DATABASE_ASYNC_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
PYTHONPATH=/app
```

**Important:** Replace `DATABASE_ASYNC_URL` prefix:
- Railway gives: `postgresql://...`
- You need: `postgresql+asyncpg://...`

You can set this manually or use a modified variable.

## Dockerfile Modifications for Railway

Railway may have issues with Playwright. Use the alternative Dockerfile.railway if needed.

## Common Issues

1. **Port binding**: Railway sets `$PORT` dynamically - the Dockerfile handles this
2. **Memory limits**: Playwright needs ~512MB+ RAM per worker
3. **Build timeout**: Playwright install takes time, may need to increase build timeout
4. **Async driver**: Ensure DATABASE_ASYNC_URL uses `postgresql+asyncpg://`
