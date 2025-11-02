# Docker Configuration

Docker Compose setup for the full stack.

## Services

-   **db**: PostgreSQL 17 (port 5432)
-   **backend**: FastAPI (port 8000)
-   **frontend**: Nginx static build (port 80)

## Usage

```bash
docker compose up -d              # Start all
docker compose --profile dev up   # Dev mode (hot reload)
docker compose down               # Stop
```

See [../docs/setup.md](../docs/setup.md) for full documentation.
