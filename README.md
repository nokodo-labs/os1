<div align="center">

<img src="https://nokodo.net/media/images/logo_full.svg" alt="nokodo" width=83% />
<div style="height: 30px;"></div>

**your AI-native workspace - chat, code, create, and control everything from one beautiful interface**

[![License](https://img.shields.io/github/license/nokodo-labs/nokodo-ai)](LICENSE)
[![Stars](https://img.shields.io/github/stars/nokodo-labs/nokodo-ai?style=social)](https://github.com/nokodo-labs/nokodo-ai/stargazers)
[![Issues](https://img.shields.io/github/issues/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/nokodo-labs/nokodo-ai)](https://github.com/nokodo-labs/nokodo-ai/pulls)
[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/node-24+-green.svg)](https://nodejs.org/)

</div>

---

nokodo is a next-gen AI platform that goes beyond chat. it combines powerful agentic capabilities with a unified workspace for conversations, autonomous coding, deep research, and life management - all wrapped in a stunning UI designed for the future.

https://github.com/user-attachments/assets/ddedb7be-1b99-4d25-b2b0-6c2dcfb28a65

> [!WARNING]
> 🚧 this project is in **prototype stage** - many features are still in development or not yet available. expect breaking changes and incomplete functionality.

---

## ✨ features

### 🤖 agentic AI

- **multi-turn agent sessions** - agents that think, act, and iterate until the job is done
- **agent delegation** - agents can spawn sub-agents for specialized tasks, each in isolated threads
- **tool use** - native, built-in tools allow agents to take actions across the entire platform and beyond
- **intelligence router** - automatically selects the right model for each query (cost optimization)

### 🔥 autonomous coding agent

- **full sandbox environment** - terminal access, code changes, test execution
- **iterative workflow** - reads code → makes changes → runs tests → refines until done
- **automatic PR creation** - pushes to GitHub and opens a pull request when complete
- **multi-model support** - use any model, extensively customizable

### 🔍 deep research

- **multi-iteration search** - AI performs comprehensive research over several minutes
- **document synthesis** - builds structured reports from multiple sources
- **async execution** - works in background, notifies when complete

### 💬 unified chats

- **mixed participants** - multiple humans and AIs in the same conversation
- **real-time AI assistance** - summarize, translate, or assist in any thread
- **branching conversations** - fork and explore alternative paths

### 🧠 intelligent memory

- **persistent context** - remembers important information across sessions
- **smart retrieval** - surfaces relevant memories when you need them
- **chat recall** - pulls context from previous conversations automatically

### 🖥️ admin console

- **separate frontend app** - dedicated Svelte-based console for admins
- **user and backend management** - monitor usage, manage users, view logs
- **secure access** - OIDC SSO, role-based permissions, audit logging

### 📂 AI-generated artifacts

- **auto-generated files** - agents can create, edit, and manage files using the Canvas tool
- **rich media support** - images, videos, documents, code files, and more
- **artifact library** - centralized storage and management of all AI-generated content

### 🎨 liquid UI

- **glassmorphism** - Apple-inspired aesthetic with depth, blur, and transparency
- **beautiful markdown** - enhanced stream rendering thanks to Vercel Streamdown
- **persistent chrome** - Island header + Dock sidebar anchor your experience

### 📱 Progressive Web App (PWA)

- **installable** - add nokodo to your desktop or mobile home screen
- **offline support** - access recent conversations and files without internet
- **push notifications** - stay informed with real-time updates

### 🛠️ built-in tools

| tool                 | capability                                              |
| -------------------- | ------------------------------------------------------- |
| **web search**       | tiered: fast basic search + deep agentic research       |
| **webpage fetch**    | scrape and parse any URL                                |
| **code execution**   | sandboxed Python with file creation                     |
| **file handling**    | upload, generate, edit, and download files              |
| **media generation** | create and edit images and videos via multiple backends |
| **memory**           | store and retrieve contextual information               |

### 🔐 enterprise-ready

- **OIDC authentication** - SSO with any provider, federated users and groups
- **role-based access** - granular permissions, invisible to end users
- **user groups** - shared threads, files, and projects with group-level quotas
- **rate limiting** - per-user, global, by time period, with clear messaging

### 📱 workspace features

- **projects** - organize threads, files, and resources together
- **notifications** - PWA push, email (SMTP), Telegram, and more
- **user groups** - share threads, files, and projects with teams

### 🌐 extensibility

- **custom tools** - add your own capabilities
- **custom filters and hooks** - modify core behaviors
- **plugin architecture** - extend with community-made additions

---

## 🛠️ stack

| layer        | technologies                                                                      |
| ------------ | --------------------------------------------------------------------------------- |
| **backend**  | FastAPI, Python 3.13+, custom AI library, SQLAlchemy 2.0+, PostgreSQL 17, Alembic |
| **frontend** | Svelte 5, Vite, Vercel Streamdown, Tailwind 4, TypeScript                         |
| **console**  | Svelte 5, Vite, shadcn-svelte, Tailwind 4, TypeScript                             |
| **infra**    | Docker Compose, Nginx, GitHub Actions, Release Please                             |

---

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

### 3. run the frontend

```bash
cd frontend && pnpm install && pnpm run dev
```

> 💡 **VS Code** - open the workspace for tasks, debugger configs, and recommended extensions.

see [docs/setup.md](docs/setup.md) for detailed setup, production deployment, and environment configuration.

---

## 🤝 contributing

contributions are welcome! please check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 license

BSD 3-Clause - see [LICENSE](LICENSE) for details.
