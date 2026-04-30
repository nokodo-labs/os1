# Docker Configuration

Two compose entrypoints support public image-based deployments and local DX.

## Files

- `docker-compose.yml` - public deployment stack. Pulls `:latest` images from GHCR and uses named volumes, so it can run without the source tree.
- `docker-compose.local.yml` - DX-friendly stack with Compose profiles. Use `deps` for infrastructure only or `local` to build/run the full stack from source.

## Usage

```bash
cd .docker

# dependencies only (for local backend/frontend processes)
docker compose -f docker-compose.local.yml --profile deps up -d

# full local stack built from the repo
docker compose -f docker-compose.local.yml --profile local up -d --build
docker compose -f docker-compose.local.yml down

# public image-based deployment stack
docker compose up -d
docker compose down
```

See [../docs/setup.md](../docs/setup.md) for the complete instructions.
