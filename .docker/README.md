# Docker Configuration

Two compose entrypoints support both local DX and production-style runs.

## Files

-   `docker-compose.yml` – DX-friendly stack with Compose profiles. Use `deps` for infrastructure only (Postgres, etc.) or `local` to build/run the full stack from source.
-   `docker-compose.production.yml` – user-facing stack that pulls prebuilt images from GHCR for staging/production parity.

## Usage

```bash
cd .docker

# dependencies only (for local backend/frontend processes)
docker compose --profile deps up -d

# full local stack built from the repo
docker compose --profile local up -d
docker compose down

# production-style run (registry images)
docker compose -f docker-compose.production.yml up -d
docker compose -f docker-compose.production.yml down
```

See [../docs/setup.md](../docs/setup.md) for the complete instructions.
