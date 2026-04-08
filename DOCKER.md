# Docker

Single-container setup — Flask serves the compiled React build via gunicorn.
No separate Node.js process or reverse proxy needed in production.

## Quick start

```bash
# 1. Clone the repo
git clone https://github.com/HamzaLatif02/finpipe.git
cd finpipe

# 2. Create a .env file
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY

# 3. Build and run
docker compose up --build

# 4. Open the app
open http://localhost:8000
```

## Build the image manually

```bash
docker build -t financial-pipeline:latest .
```

First build takes 3–5 minutes (Node build + pip install).
Subsequent builds use the layer cache and are much faster.

## Run with docker run

```bash
docker run \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e SECRET_KEY=your-secret-key \
  -e ANTHROPIC_API_KEY=your-key \
  -e RESEND_API_KEY=your-key \
  -e FLASK_ENV=production \
  financial-pipeline:latest
```

## Environment variables

| Variable              | Required | Default      | Description                          |
|-----------------------|----------|--------------|--------------------------------------|
| SECRET_KEY            | Yes      | —            | Flask session secret                 |
| ANTHROPIC_API_KEY     | No       | (empty)      | For AI chart descriptions            |
| RESEND_API_KEY        | No       | (empty)      | For email report delivery            |
| DATABASE_URL          | No       | (empty)      | PostgreSQL for scheduled jobs        |
| ADMIN_TOKEN           | No       | (empty)      | For /api/schedule/admin endpoint     |
| RATELIMIT_STORAGE_URI | No       | memory://    | Rate limit storage backend           |
| RENDER_EXTERNAL_URL   | No       | localhost    | Public URL for confirmation emails   |
| PORT                  | No       | 8000         | Port gunicorn listens on             |

## Data persistence

Reports, charts, and the SQLite database are written to `data/`.
Mount it as a volume so data survives container restarts:

```bash
docker run -v ./data:/app/data ...
# or with compose (already configured in docker-compose.yml)
docker compose up
```

Without the volume mount, all generated reports are lost when the container stops.

## Production deployment

```bash
# Build and tag
docker build -t financial-pipeline:latest .

# Run with prod compose (reads from .env automatically)
docker compose -f docker-compose.prod.yml up -d
```

## Updating

```bash
docker compose down
docker compose up --build
```

## Health check

```bash
curl http://localhost:8000/api/health
# {"status": "ok", "scheduler_running": true}
```

Docker checks this endpoint every 30 seconds and restarts the container if it fails 3 times.
