<div align="center">

<img src="https://nokodo.net/media/images/logo_full.svg" alt="nokodo" width="320" />

**open-source AI platform with agentic coding, liquid UI, and full-stack type safety**

[![License](https://img.shields.io/github/license/nokodo-labs/nokodo-ai)](LICENSE)
[![Stars](https://img.shields.io/github/stars/nokodo-labs/nokodo-ai?style=social)](https://github.com/nokodo-labs/nokodo-ai/stargazers)
[![Issues](https://img.shields.io/github/issues/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/pulls)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-24+-green.svg)](https://nodejs.org/)

</div>

---

## ✨ features

-   🤖 **agentic AI** - multi-turn agent sessions with tool use, delegation, and async task execution
-   🎨 **liquid UI** - apple-inspired glassmorphism with physics-based animations
-   🔧 **built-in tools** - web search, memory, code execution, file handling, and more
-   🧵 **unified threads** - one abstraction for user↔agent, user↔user, and agent↔agent conversations
-   🔒 **full-stack type safety** - python type hints → openapi → auto-generated typescript client
-   🏗️ **production-ready** - postgres, docker, nginx, CI/CD, migrations out of the box

## 🛠️ stack

| layer        | technologies                                                                |
| ------------ | --------------------------------------------------------------------------- |
| **backend**  | FastAPI, Python 3.13+, Pydantic AI, SQLAlchemy 2.0+, PostgreSQL 17, Alembic |
| **frontend** | Svelte 5, Vite, Vercel AI SDK, shadcn-svelte, Tailwind 4, TypeScript        |
| **console**  | Svelte 5, Vite, shadcn-svelte, Tailwind 4, TypeScript                       |
| **infra**    | Docker Compose, Nginx, GitHub Actions, Release Please                       |

## 🚀 quick start

### 1. start dependencies

```bash
cd .docker && docker compose --profile deps up -d
```

### 2. run the backend

```bash
cd backend
uv sync --all-extras
cp .env.example .env
uv run uvicorn api.main:app --reload
```

### 3. run the frontends

```bash
cd frontend && npm install && npm run dev
cd console && npm install && npm run dev -- --host --port 8383
```

> 💡 **VS Code**: open the workspace for tasks, debugger configs, and recommended extensions.

> 💡 **full containers**: `docker compose --profile local up -d` from `.docker/` for parity checks.

See [docs/setup.md](docs/setup.md) for detailed setup, production deployment, and environment configuration.

## 🤝 contributing

contributions are welcome! please check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 license

BSD 3-Clause - see [LICENSE](LICENSE) for details.
