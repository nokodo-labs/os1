<div align="center">

# Monorepo Template

**Modern full-stack boilerplate: FastAPI backend + Svelte 5 frontend with containerization, VS Code support, and AI integrations.**

[![License](https://img.shields.io/github/license/nokodo-labs/monorepo-template)](LICENSE)
[![Stars](https://img.shields.io/github/stars/nokodo-labs/monorepo-template?style=social)](https://github.com/nokodo-labs/monorepo-template/stargazers)
[![Issues](https://img.shields.io/github/issues/nokodo-labs/monorepo-template)](https://github.com/nokodo-labs/monorepo-template/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/nokodo-labs/monorepo-template)](https://github.com/nokodo-labs/monorepo-template/pulls)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-24+-green.svg)](https://nodejs.org/)

</div>

## Stack

-   **Backend**: FastAPI (Python 3.13+), SQLAlchemy 2.0+, Pydantic, PostgreSQL 17, Alembic
-   **Frontend**: Svelte 5, TypeScript, Vite 6, TailwindCSS, native fetch (zero HTTP deps)
-   **Type Safety**: OpenAPI TypeScript generator (auto-sync backend → frontend types)
-   **Dev**: VS Code (tasks, debugger, extensions), Ruff, pytest
-   **Deploy**: Docker Compose with production configs

## Quick Start

### 1. Customize Template

**First time setup**: Rename `backend/project_slug/` and update references. See [docs/setup.md](docs/setup.md) for details.

### 2. Start Services

```bash
cd .docker
docker compose up -d
```

-   Frontend: http://localhost (Nginx)
-   Backend API: http://localhost:8000
-   API Docs: http://localhost:8000/v1/docs

Deploys:

-   GitHub Pages via pipeline (PR previews + production/stable publishes)
-   Custom domain supported (CNAME to `<user>.github.io`)

On Pages the header status shows `preview` (no API polling).

## Structure

```
backend/
├── api/                   # FastAPI application
│   ├── api/v1/endpoints/  # Route handlers
│   ├── core/              # Config, database
│   ├── models/            # SQLAlchemy ORM
│   ├── schemas/           # Pydantic validation
│   └── tests/             # API & ORM tests
├── project_slug/          # SDK/service layer (rename me!)
│   └── tests/             # SDK unit tests (optional)
├── tests/                 # E2E integration tests
├── data/                  # Data storage (volume mounted)
└── alembic/               # Database migrations

frontend/
├── src/
│   ├── lib/               # Components
│   └── main.ts            # Entry point
└── nginx.conf             # Production server

.docker/                   # Docker configs
├── Dockerfile.backend     # Backend build
├── Dockerfile.frontend    # Frontend build
├── docker-compose.yml     # Production
└── docker-compose.dev.yml # Development

.github/                   # CI/CD, Dependabot, CODEOWNERS
.vscode/                   # Editor config, tasks, debugger
tools/release_please/      # Release automation config
```

### Architecture

**Backend:**

-   **`api/`**: FastAPI app, routes, ORM, database setup
-   **`project_slug/`**: Business logic SDK that can be packaged separately for pip distribution
-   **Testing**: 3 tiers (API tests in `api/tests/`, SDK tests in `project_slug/tests/`, E2E in `tests/`)
-   **URLs**: `/v1/users` (no `/api` prefix - deploy on `api.yourdomain.com`)

**Frontend:**

-   **Native fetch** - Zero HTTP library dependencies, uses web standards
-   **OpenAPI types** - Auto-generated TypeScript types from FastAPI schema
-   **Type safety** - Backend changes = compile errors in frontend if incompatible

**Customization Required Before Use:** See [docs/setup.md](docs/setup.md) for complete setup instructions.

## Configuration

See [docs/setup.md](docs/setup.md) for environment variable setup and configuration details.

To use this as your own starter: click “Use this template” on GitHub, create your repo, then follow [docs/setup.md](docs/setup.md).

## Commands

See [docs/setup.md](docs/setup.md) for full command reference.

```bash
# Quick reference
cd .docker && docker compose up -d    # Start all services
cd backend && pytest -v               # Run tests
cd frontend && npm run dev            # Dev server
```

## VS Code

-   Install recommended extensions (prompt on open)
-   Use tasks: Ctrl+Shift+P → "Tasks: Run Task"
-   Debug: F5 → Choose "Python: FastAPI" or "Frontend: Chrome"

## Features

-   ✅ Python 3.13+, Node 24+ enforced
-   ✅ Full type safety: Python type hints, TypeScript strict, OpenAPI auto-sync
-   ✅ Modern: Native fetch (no axios/HTTP lib deps), Svelte 5 runes, FastAPI
-   ✅ Tabs + unix line endings (editorconfig)
-   ✅ Ruff: format, lint, import sorting
-   ✅ Hot reload: backend + frontend
-   ✅ Data directory: `backend/data/` (volume mounted)
-   ✅ Production ready: multi-stage builds, Nginx
-   ✅ Tests: pytest with async fixtures
-   ✅ Minimal: no business logic, easily customizable
-   ✅ Future-proof: Built on web standards, no legacy dependencies

## License

BSD 3-Clause - See [LICENSE](LICENSE) for details.
