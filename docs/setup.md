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

### Database Only

```bash
cd .docker
docker compose up db -d
```

## VS Code

1. Install recommended extensions
2. Select Python interpreter: `./backend/.venv/bin/python`
3. Use tasks (Ctrl+Shift+P → "Tasks: Run Task")

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
alembic revision --autogenerate -m "Description"
alembic upgrade head
alembic downgrade -1
```

## Production Build

```bash
cd .docker
docker compose build
docker compose up -d
```

Frontend served via Nginx on http://localhost

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
alembic revision --autogenerate -m "Description"  # Create migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one

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

1. Click “Use this template” on GitHub and create your new repository
2. Clone your new repository locally
3. Follow the steps in “Initial Customization” above
4. Push your changes; your CI/CD will run and GitHub Pages (via the pipeline) will publish previews for PRs and deploy on `production`/`stable`

**Types out of sync**: Run `npm run generate:api-types` after backend changes
