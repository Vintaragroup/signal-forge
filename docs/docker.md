# Docker

## Services

```bash
docker compose up --build
```

## API

The API is exposed on port `8000`.

```bash
curl http://localhost:8000/health
```

## Run A Single Worker

```bash
docker compose run --rm lead_scraper
docker compose run --rm lead_enricher
docker compose run --rm social_processor
docker compose run --rm post_generator
```

## MongoDB

MongoDB is exposed locally on port `27017`.

Default internal URI:

```text
mongodb://mongo:27017/signalforge
```

Default host URI:

```text
mongodb://localhost:27017/signalforge
```

Mongo data is stored in the named Docker volume `signalforge_mongo-data`.

## Vault Mount

Every service mounts:

```text
./vault:/vault
```

Services should read prompts from `/vault/prompts` and write human-readable outputs into the appropriate vault folder.

## Redis Service

Redis is used as the render job queue for the Social Creative Engine v5 pipeline.

```bash
# Verify Redis is healthy
docker compose exec redis redis-cli ping
# → PONG

# Check queue depth
docker compose exec redis redis-cli llen signalforge:render_jobs

# Inspect dead-letter queue
docker compose exec redis redis-cli lrange signalforge:render_jobs_failed 0 -1
```

## Worker Service

The worker container (`signalforge-worker`) uses the same Docker image as the API but runs `python worker.py` instead of `uvicorn`. It polls Redis for render jobs and processes them through the ComfyUI → FFmpeg pipeline.

```bash
# View worker logs
docker compose logs -f worker

# Restart worker after code change
docker compose build api && docker compose restart worker

# Run one job then exit (smoke test)
docker compose exec worker python worker.py --once
```

## ComfyUI Service (Optional Profile)

ComfyUI is not started by default. Enable it with the `comfyui` Docker Compose profile:

```bash
# Start with ComfyUI stub (local dev)
docker compose --profile comfyui up -d

# Stop and remove ComfyUI container
docker compose --profile comfyui down
```

`COMFYUI_ENABLED=false` (default) means the worker uses the mock render path even if the container is running. Set `COMFYUI_ENABLED=true` in `.env` to route real ComfyUI calls to the service.

## Render Output Volume

The `render-output` Docker volume is shared between the api and worker containers at `/tmp/signalforge_renders`. With `FFMPEG_ENABLED=true` (default in v5.5), real `.mp4` files, test-tone `.wav` files, and placeholder `.png` files are written here.

```bash
# Inspect rendered files (from api container)
docker compose exec api ls -lh /tmp/signalforge_renders/

# Verify FFmpeg binary is installed in both containers
docker compose exec api ffmpeg -version
docker compose exec worker ffmpeg -version

# Check FFmpeg health via API
curl http://localhost:8000/health/ffmpeg

# Watch worker logs for FFmpeg diagnostics at startup
docker compose logs worker | grep -i ffmpeg
```

## v5.5 Rebuild Requirements

When updating Python files (video_assembler.py, worker.py, main.py), **both** api and worker images must be rebuilt:

```bash
docker compose build --no-cache api worker
docker compose up -d
```

> The api and worker containers share the same Dockerfile but produce separate images. Rebuilding `api` does not rebuild `worker`.

## Disabling FFmpeg (revert to mock)

```bash
FFMPEG_ENABLED=false docker compose up -d
# OR
echo "FFMPEG_ENABLED=false" >> .env && docker compose up -d
```
