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
-   **`frontend/.env`**: Create from `.env.example` and set `VITE_API_URL`

### 4. Customize AI Instructions (Optional)

-   **`.github/copilot-instructions.md`**: Update project title and add project-specific patterns
-   **`.github/instructions/`**: Add domain-specific instruction files (see [.github/instructions/README.md](../.github/instructions/README.md))

## Quick Start

```bash
cd .docker
docker compose up -d
```

Access:

-   Frontend: http://localhost (Nginx)
-   Backend: http://localhost:8000

## Local Development

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
docker compose up db -d
```

## Testing

```bash
# Backend
cd backend
pytest -v
pytest --cov=app tests/

# Frontend
cd frontend
npm run test
```

## Docker Commands

```bash
cd .docker

# Start/stop
docker compose up -d
docker compose down
docker compose down -v  # Delete volumes

# Logs
docker compose logs -f [service]

# Rebuild
docker compose up -d --build
```

## Database Migrations

```bash
cd backend
alembic -c api/alembic.ini revision --autogenerate -m "Description"
alembic -c api/alembic.ini upgrade head
alembic -c api/alembic.ini downgrade -1
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
# Create production compose file
cd .docker

# Update docker-compose.yml to use GHCR images:
# Change build: context to: image: ghcr.io/your-org/your-repo:latest

# Pull and start
docker compose pull
docker compose up -d
```

### Building Locally

```bash
cd .docker
docker compose build
docker compose up -d
```

Frontend served via Nginx on http://localhost

## Production Deployment

### Environment Configuration

**Required: Update these values for production**

#### backend/.env

```
DATABASE_URL=postgresql+psycopg://user:password@db:5432/app_db
SECRET_KEY=generate-secure-random-key-here
DEBUG=False
APP_ENV=production
CORS_ORIGINS='["https://yourdomain.com"]'
```

#### docker-compose.yml

Update the following in `.docker/docker-compose.yml`:

1. **Database credentials**: Change `POSTGRES_PASSWORD`
2. **Backend SECRET_KEY**: Use a secure random key
3. **CORS_ORIGINS**: Add your production domain(s)
4. **Image sources**: Switch from `build:` to `image: ghcr.io/your-org/your-repo:latest`

### Deployment Steps

1. **Configure environment** - Update `.env` files and `docker-compose.yml`
2. **Pull images** - `docker compose pull` (or build locally)
3. **Start services** - `docker compose up -d`
4. **Run migrations** - `docker compose exec backend alembic -c api/alembic.ini upgrade head`
5. **Verify** - Check logs with `docker compose logs -f`

### Container Registry Access

Images are public by default. For private images:

```bash
# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull images
docker compose pull
```

### Updating Production

```bash
# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d

# Run any new migrations
docker compose exec backend alembic -c api/alembic.ini upgrade head
```

### Optional: GitHub Pages (Frontend Only)

The template includes CI/CD for deploying the frontend build to GitHub Pages for static hosting. This is separate from the Docker deployment and only hosts the frontend.

Configure in repository settings: Settings → Pages → Source: GitHub Actions

## Environment Variables

### backend/.env

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/app_db
DEBUG=True
SECRET_KEY=change-in-production
```

### frontend/.env

```
VITE_API_URL=http://localhost:8000/v1
VITE_PAGES=false
```

## All Commands Reference

### Docker (from .docker/)

```bash
docker compose up -d              # Start all services
docker compose down               # Stop services
docker compose down -v            # Stop and remove volumes
docker compose logs -f [service]  # View logs
docker compose up -d --build      # Rebuild and start
docker compose --profile dev up   # Dev mode (hot reload)
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
alembic -c api/alembic.ini revision --autogenerate -m "Description"  # Create migration
alembic -c api/alembic.ini upgrade head                              # Apply migrations
alembic -c api/alembic.ini downgrade -1                              # Rollback one

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
