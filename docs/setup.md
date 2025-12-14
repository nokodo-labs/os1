# Setup & Customization

These steps are for developers who created a new repository using the “Use this template” button from this template.

## Initial Customization (Required)

After creating your repository from this template, customize the project:

### 1. Rename Project Package

```bash
# Rename the SDK package
cd backend
mv project_slug your-project-slug
```

### 2. Update References

Search and replace throughout the codebase:

-   `"project-title"` → `"Your Full Project Title"` (used in documentation headers and release PR titles)
-   `"project-slug"` → `"your-project-slug"` in `tools/release_please/*.json`
-   `from project_slug` → `from your_project_slug` in Python imports
-   `PROJECT_NAME = "FastAPI Monorepo"` → your project name in `backend/api/core/config.py`
-   `frontend/package.json`: Update `name` field

### 3. Configure Team & Environment

-   **`.github/CODEOWNERS`**: Add your GitHub handles
-   **`backend/.env`**: Create from `.env.example` and set `SECRET_KEY`, `DATABASE_URL`
-   **`frontend/.env`**: Create from `.env.example` (optional fallbacks only)

### 4. Customize AI Instructions (Optional)

-   **`.github/copilot-instructions.md`**: Update project title and add project-specific patterns
-   **`.github/instructions/`**: Add domain-specific instruction files (see [.github/instructions/README.md](../.github/instructions/README.md))

## Quick Start

```bash
cd .docker
docker compose --profile deps up -d
```

This boots Postgres locally so you can run the backend/frontend straight from your IDE with instant reloads and debuggers.

Need to preview the full containerized stack? `docker compose --profile local up -d` is available in this folder.

## Local Development

> Start Postgres before running any app processes:
>
> ```bash
> cd .docker
> docker compose --profile deps up -d
> ```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1  # Windows
pip install -e .[api,dev]
cp .env.example .env
uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env

The frontend uses stable paths (e.g. `/v1`) and loads runtime config from the backend at `/v1/system/config`.
Configure `PUBLIC_API_URL` / `PUBLIC_CDN_URL` in `backend/.env` when needed.

# Generate API types (requires backend running)
npm run generate:api-types

npm run dev
```

**Type Generation**: Run `npm run generate:api-types` whenever backend API changes to sync TypeScript types.

## VS Code Setup

The template includes comprehensive VS Code integration that works automatically:

### What's Included

**Automatic Configuration:**

-   Python interpreter auto-selected from `backend/.venv`
-   Format on save with Ruff (Python) and Prettier (JS/TS/Svelte)
-   Auto-organize imports and fix lint errors
-   pytest test discovery
-   Tailwind CSS IntelliSense

**Tasks** (`Ctrl+Shift+P` → "Tasks: Run Task"):

-   **Backend**: Install Dependencies, Run Server, Run Tests
-   **Frontend**: Install Dependencies, Dev Server, Build
-   **Docker**: Build All, Up, Down, Dev Mode

**Debug Configurations** (Press `F5`):

-   **Python: FastAPI** - Debug backend server
-   **Python: Current File** - Debug active Python file
-   **Python: Pytest** - Debug current test file
-   **Frontend: Vite Dev Server** - Launch frontend dev server
-   **Frontend: Chrome** - Debug frontend in Chrome
-   **Docker: Attach to Backend** - Attach to running container
-   **Full Stack** (Compound) - Runs backend + frontend + Chrome together

**Recommended Extensions** (auto-prompt on workspace open):

-   Python, Pylance, Ruff
-   Svelte, Tailwind CSS, Prettier, ESLint
-   Docker, Remote Containers
-   GitLens, GitHub Actions
-   GitHub Copilot, Claude Code
-   And more (see `.vscode/extensions.json`)

### Quick Start

1. Open workspace in VS Code
2. Accept prompt to install recommended extensions
3. Press `F5` → Choose **"Full Stack"** to run everything at once

### Database Only

```bash
cd .docker
docker compose --profile deps up -d
```

## Testing

> Tests require a running Postgres instance. Start the dependency compose file (see above) or ensure `DATABASE_URL` points at a reachable Postgres database.

```bash
# Backend
cd backend
pytest -v
pytest --cov=api --cov=nokodo_ai

# Frontend
cd frontend
npm run test
```

-   Set `TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db_name` to override the template used for per-test disposable databases.
-   Set `TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres` only if `TEST_DATABASE_URL` does not have permission to create/drop databases.

## Docker Commands

```bash
cd .docker

# Start/stop
docker compose --profile deps up -d        # Dependencies only
docker compose --profile local up -d       # Full local stack
docker compose down                        # Stop whatever is running
docker compose down -v                     # Stop and delete volumes
docker compose -f docker-compose.production.yml up -d     # Production-style run
docker compose -f docker-compose.production.yml down

# Logs
docker compose logs -f [service]

# Rebuild local stack
docker compose --profile local up -d --build
```

## Database Migrations

```bash
cd backend
alembic -c api/migrations/alembic.ini upgrade head                     # Apply every pending migration
alembic -c api/migrations/alembic.ini revision --autogenerate -m "Description"  # Create a new revision from models
alembic -c api/migrations/alembic.ini downgrade -1                     # Roll back the last revision
alembic -c api/migrations/alembic.ini downgrade base                   # Roll back everything to an empty DB
alembic -c api/migrations/alembic.ini history                          # Show the chronological migration log
alembic -c api/migrations/alembic.ini current                          # Display the revision currently applied
alembic -c api/migrations/alembic.ini heads                            # List all branch heads
alembic -c api/migrations/alembic.ini show <revision>                  # Inspect a specific revision
alembic -c api/migrations/alembic.ini stamp head                       # Mark the DB as up-to-date without running migrations
```

## Production Build

### Using Pre-built Images (Recommended)

CI/CD automatically builds and publishes Docker images to GitHub Container Registry on every commit.

**Image tags:**

-   `ghcr.io/your-org/your-repo:latest` - Latest production release
-   `ghcr.io/your-org/your-repo:dev` - Latest dev branch
-   `ghcr.io/your-org/your-repo:v1.2.3` - Specific version releases
-   `ghcr.io/your-org/your-repo:abc1234` - Specific commit

**Deploy with pre-built images:**

```bash
cd .docker
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
```

### Building Locally

```bash
cd .docker
docker compose --profile local up -d --build
```

Frontend served via Nginx on http://localhost

## Production Deployment

### Environment Configuration

**Required: Update these values for production**

#### backend/.env

```
DATABASE_URL=postgresql+psycopg://nokodo-ai-admin:nokodo-ai@db:5432/nokodo-ai-production
SECRET_KEY=generate-secure-random-key-here
DEBUG=False
APP_ENV=production
CORS_ORIGINS='["https://yourdomain.com"]'
```

#### docker-compose.production.yml

Update the following in `.docker/docker-compose.production.yml`:

1. **Database credentials**: Change `POSTGRES_PASSWORD`
2. **Backend SECRET_KEY**: Use a secure random key
3. **CORS_ORIGINS**: Add your production domain(s)

### Deployment Steps

1. **Configure environment** - Update `.env` files and `.docker/docker-compose.production.yml`
2. **Pull images** - `docker compose -f docker-compose.production.yml pull` (or build locally)
3. **Start services** - `docker compose -f docker-compose.production.yml up -d`
4. **Run migrations** - `docker compose -f docker-compose.production.yml exec backend alembic -c api/migrations/alembic.ini upgrade head`
5. **Verify** - Check logs with `docker compose -f docker-compose.production.yml logs -f`

### Container Registry Access

Images are public by default. For private images:

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull images
docker compose -f docker-compose.production.yml pull
```

### Updating Production

```bash
# Pull latest images
docker compose -f docker-compose.production.yml pull

# Restart with new images
docker compose -f docker-compose.production.yml up -d

# Run any new migrations
docker compose -f docker-compose.production.yml exec backend alembic -c api/migrations/alembic.ini upgrade head
```

### Optional: GitHub Pages (Frontend Only)

The template includes CI/CD for deploying the frontend build to GitHub Pages for static hosting. This is separate from the Docker deployment and only hosts the frontend.

Configure in repository settings: Settings → Pages → Source: GitHub Actions

## Environment Variables

### backend/.env

```
DATABASE_URL=postgresql+psycopg://nokodo-ai-admin:nokodo-ai@127.0.0.1:5432/nokodo-ai-dev
TEST_DATABASE_URL=postgresql+psycopg://nokodo-ai-admin:nokodo-ai@127.0.0.1:5432/nokodo-ai-dev
TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres
DEBUG=True
SECRET_KEY=change-in-production
```

Optional: override `TEST_DATABASE_URL` when you want pytest to create databases from a different template, and set `TEST_DATABASE_ADMIN_URL` when the Postgres superuser credentials differ from your application credentials. The test harness now creates and drops a unique Postgres database for every test case using these values.

### frontend/.env

```
VITE_API_URL=http://localhost:8000/v1
VITE_PAGES=false
```

## All Commands Reference

### Docker (from .docker/)

```bash
docker compose --profile deps up -d        # Start shared services only
docker compose --profile local up -d       # Full stack (backend + frontend)
docker compose down                        # Stop services
docker compose down -v                     # Stop and remove volumes
docker compose logs -f [service]           # View logs
docker compose --profile local up -d --build   # Rebuild and start
docker compose -f docker-compose.production.yml up -d   # Production stack
docker compose -f docker-compose.production.yml down
```

### Backend (from backend/)

```bash
# Testing
pytest -v                                    # Run all tests
pytest api/tests/ -v                         # API tests only
pytest project_slug/tests/ -v               # SDK tests only
pytest --cov=api --cov=project_slug tests/   # E2E with coverage

# Code quality
ruff format .                     # Format code
ruff check . --fix                # Lint + autofix

# Database migrations
alembic -c api/migrations/alembic.ini revision --autogenerate -m "Description"  # Create migration
alembic -c api/migrations/alembic.ini upgrade head                              # Apply migrations
alembic -c api/migrations/alembic.ini downgrade -1                              # Rollback one

# Development
uvicorn api.main:app --reload     # Start dev server
```

### Frontend (from frontend/)

```bash
npm run dev                       # Start dev server
npm run build                     # Production build
npm run preview                   # Preview production build
npm run lint                      # Lint code
npm run generate:api-types        # Generate TypeScript types from OpenAPI
```

## Troubleshooting

**Port conflicts**: Change ports in `.docker/docker-compose.yml`

**DB connection failed**: `docker compose restart db`

**Python imports**: Ensure `PYTHONPATH=./backend` (VS Code sets automatically)

**Module not found**: Delete `node_modules`, run `npm install`

## Using this Template

1. Click "Use this template" on GitHub and create your new repository
2. Clone your new repository locally
3. Follow the steps in "Initial Customization" above
4. Push your changes - CI/CD will automatically build and publish Docker images to GHCR
5. Deploy using pre-built images (see [Production Deployment](#production-deployment))

**Types out of sync**: Run `npm run generate:api-types` after backend changes
