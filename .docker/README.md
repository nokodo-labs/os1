# Docker configuration

two compose entrypoints support public image-based deployments and local DX.

## files

- `docker-compose.yml` - public deployment stack. pulls `:latest` images from GHCR and uses named volumes, so it can run without the source tree.
- `docker-compose.local.yml` - DX-friendly stack with Compose profiles. use `deps` for infrastructure only or `local` to build/run the full stack from source.

## required services

postgres and valkey/redis are both hard dependencies of the API, not optional accelerators.

## usage

the public deployment stack requires a few secrets to be present in the environment.
supply them however your platform prefers: a shell export, a Portainer/NAS stack env field, or a `.env` file next to the compose:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- `NOKODO__SECURITY__SECRET_KEY` (e.g. `python -c "import secrets; print(secrets.token_urlsafe(64))"`)
- `NOKODO__SECURITY__CORS_ORIGINS`, `NOKODO__BRANDING__PUBLIC_FRONTEND_ORIGIN`

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

see [../docs/setup.md](../docs/setup.md) for the complete instructions.
