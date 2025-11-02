<div align="center">

<img src="https://nokodo.net/media/images/logo_full.svg" alt="nokodo logo" width="320" />
<div style="height:32px"></div>

---

<h1>nokodo AI</h1>

**Modern AI platform with agentic coding support, built for seamless developer experience and beautiful user interfaces.**

[![License](https://img.shields.io/github/license/nokodo-labs/nokodo-ai)](LICENSE)
[![Stars](https://img.shields.io/github/stars/nokodo-labs/nokodo-ai?style=social)](https://github.com/nokodo-labs/nokodo-ai/stargazers)
[![Issues](https://img.shields.io/github/issues/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/pulls)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-24+-green.svg)](https://nodejs.org/)

</div>

## 🛠️ Stack

-   **Backend**: FastAPI (Python 3.13+), Pydantic AI, SQLAlchemy 2.0+, PostgreSQL 17, Alembic
-   **Frontend**: Svelte 5, Vite 6, Vercel AI SDK, shadcn-svelte, Tailwind 4, TypeScript
-   **Type Safety**: OpenAPI TypeScript generator (auto-sync backend → frontend types)
-   **Dev**: VS Code (tasks, debugger, extensions), Ruff, pytest, AI instructions
-   **Deploy**: Docker Compose with production configs

## ✨ Features

-   🤖 **AI Agentic Coding**: Heavy AI agent support baked directly into the platform
-   🎨 **Liquid Glass UI**: Apple-inspired aesthetic with physics-based animations
-   🔧 **Built-in Tools**: Web search, webpage fetch, memory system, code execution, file handling
-   🧠 **Smart Memory**: Asynchronous memory manager with high-accuracy context retrieval
-   🔄 **Async Task System**: Multi-turn agentic sessions for deep research and complex workflows
-   🔐 **Enterprise Auth**: OIDC authentication with federated users and groups
-   ⚡ **Rate Limiting**: Granular controls per user, global, by time period
-   🔔 **Notifications**: Multi-backend support (PWA, email, Telegram)
-   🏗️ **Production Infrastructure**: PostgreSQL 17, multi-stage Docker builds, Nginx configs
-   🔒 **End-to-end Type Safety**: Python type hints → OpenAPI → auto-generated TypeScript types

## 🚀 Quick Start

### 1️⃣ Start Development

```bash
cd .docker
docker compose up -d
```

**Your services:**

-   Frontend: http://localhost
-   Backend API: http://localhost:8000
-   API Docs: http://localhost:8000/v1/docs

> 💡 **VS Code users**: Open the workspace to get tasks, debugger configs, and recommended extensions automatically.

### 2️⃣ Deploy to Production

CI/CD automatically builds and pushes Docker images to **GitHub Container Registry (GHCR)** on every commit. Images are tagged as:

-   `ghcr.io/nokodo-labs/nokodo-ai:latest` → production branch
-   `ghcr.io/nokodo-labs/nokodo-ai:dev` → dev branch
-   `ghcr.io/nokodo-labs/nokodo-ai:v1.2.3` → releases

**Deploy with Docker:**

```bash
# Pull pre-built images and deploy
docker compose pull
docker compose up -d
```

> 💡 **Tip**: See [docs/setup.md](docs/setup.md#production-deployment) for full deployment instructions and environment configuration.

## 📁 Structure

```
backend/
├── api/                   # FastAPI application
│   ├── api/v1/endpoints/  # Route handlers
│   ├── core/              # Config, database
│   ├── models/            # SQLAlchemy ORM
│   ├── schemas/           # Pydantic validation
│   ├── tests/             # API & ORM tests
│   └── alembic/           # Database migrations
├── nokodo_ai/            # SDK/service layer
│   └── tests/             # SDK unit tests
├── tests/                 # E2E integration tests
└── data/                  # Data storage (volume mounted)

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

### 🏗️ Architecture

**Backend:**

-   **`api/`**: FastAPI app, routes, ORM, database setup
-   **`nokodo_ai/`**: Business logic SDK that can be packaged separately for pip distribution
-   **Testing**: 3 tiers (API tests in `api/tests/`, SDK tests in `project_slug/tests/`, E2E in `tests/`)
-   **URLs**: `/v1/users` (no `/api` prefix - deploy on `api.yourdomain.com`)

**Frontend:**

-   **Native fetch** - Zero HTTP library dependencies, uses web standards
-   **OpenAPI types** - Auto-generated TypeScript types from FastAPI schema
-   **Type safety** - Backend changes = compile errors in frontend if incompatible

## 📄 License

BSD 3-Clause - See [LICENSE](LICENSE) for details.
