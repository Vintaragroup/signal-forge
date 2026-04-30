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
