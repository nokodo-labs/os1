<div align="center">

<img src="https://nokodo.net/static/os1/logo-sidebar.svg" alt="nokodo" width=83% />
<div style="height: 30px;"></div>

**the AI workspace you actually want to use**

[![Stars](https://img.shields.io/github/stars/nokodo-labs/os1?style=social)](https://github.com/nokodo-labs/os1/stargazers)
[![Discord](https://img.shields.io/badge/discord-join-5865F2)](https://discord.gg/VsYwyTqzDM)
[![Issues](https://img.shields.io/github/issues/nokodo-labs/os1)](https://github.com/nokodo-labs/os1/issues)

</div>

---

nokodo is an intuitive, accessible and powerful open-source AI platform.
it combines autonomous agents, deep research, real-time collaboration, and a flexible tool system - all in a beautiful, self-hostable workspace.

https://github.com/user-attachments/assets/ddedb7be-1b99-4d25-b2b0-6c2dcfb28a65

> [!WARNING]
> 🚧 this project is in **alpha stage** - many features are still in development or not yet available. expect breaking changes and incomplete functionality.

**links:** [docs](docs/setup.md) · [roadmap](ROADMAP.md) · [contributing](CONTRIBUTING.md) · [discord](https://discord.gg/VsYwyTqzDM)

---

## ✨ features

### 🤖 autonomous AI agents

- **multi-turn agent sessions** - agents that plan, act, and iterate until the job is done
- **agent delegation** - agents spawn sub-agents for specialized tasks, each in isolated context
- **native tool use** - agents can search the web, execute code, manage files, generate media, and more
- **intelligence router** - automatically picks the right model for each query, minimizing cost

### 🔥 coding agent

- **full sandbox environment** - terminal access, file editing, test execution via E2B
- **end-to-end workflow** - reads code → makes changes → runs tests → refines until complete
- **automatic PR creation** - pushes changes to GitHub and opens a pull request when done
- **any model, fully customizable** - bring your own provider and tune every parameter

### 🔍 deep research

- **multi-iteration search** - AI plans and executes comprehensive research over several minutes
- **document synthesis** - builds structured reports from multiple sources and searches
- **runs in background** - async execution, notifies when done

### 💬 collaborative chats

- **real-time collaboration** - WebSocket-based live UX lets multiple users work in the same thread simultaneously, with instant updates for everyone
- **mixed participants** - humans and AI models share the same conversation naturally
- **thread branching** - fork any message to explore alternative paths without losing context
- **real-time AI assistance** - summon AI to summarize, translate, or assist inline at any time

### 🧠 persistent memory

- **remembers what matters** - stores important context across sessions automatically
- **smart retrieval** - surfaces relevant memories when they are most useful
- **conversation recall** - pulls context from past threads into new ones seamlessly

### ✍️ powerful prompting engine

- **Jinja2-based rendering** - full template language with variables, conditionals, and loops
- **composable prompts** - prompts can include other prompts for modular, reusable building blocks
- **runtime context injection** - user preferences, conversation state, and tool results are injected automatically at render time
- **validation** - circular reference detection, depth limiting, and strict undefined enforcement

### 📊 native tracking _(coming soon)_

- **token usage per message** - tracks input, output, and cache tokens at the message level
- **cost accounting** - maps usage to model pricing for per-user and per-group spend visibility
- **activity over time** - full audit trail of user activity, requests, and resource consumption
- **admin dashboards** - monitor platform health, usage trends, and anomalies from the console

### 📂 AI-generated artifacts

- **canvas tool** - agents create, edit, and refine files directly in the conversation
- **rich media** - images, videos, code, documents - any AI output becomes a managed artifact
- **artifact library** - centralized storage for all AI-generated content

### 📱 Progressive Web App

- **installable** - add nokodo to your desktop or mobile home screen from any browser
- **push notifications** - real-time alerts even when the app is in the background
- **native iOS and Android apps** - coming soon

### 🎨 liquid UI

- **glassmorphism design** - Apple-inspired aesthetic with depth, blur, and transparency
- **beautiful markdown** - enhanced streaming rendering powered by Vercel Streamdown
- **persistent chrome** - Island header and Dock sidebar keep you oriented at all times

### 🔐 enterprise-ready

- **OIDC / SSO** - federated login with any identity provider
- **role-based access** - granular permissions, invisible to end users
- **user groups** - shared threads, files, and projects with group-level quotas
- **rate limiting** - per-user and global limits, by time period, with clear user-facing messages
- **audit logging** - full record of admin actions and system events

### 🛠️ built-in tools

- **resouce management** - native tools for managing notes, reminders, files, chats, and more
- **memory system** - automatically stores and retrieves important context across sessions
- **web search** - up-to-date information from the web, with source citations

### 🖥️ admin console

- **dedicated app** - separate Svelte-based console for platform administrators
- **user management** - create, edit, suspend users and groups
- **usage monitoring** - view logs, track activity, manage settings

### 🌐 extensibility

- **custom tools** - add new capabilities with minimal boilerplate
- **filters and hooks** - modify context injection and post-response behavior
- **plugin architecture** - extend with community-built additions

### 🖌️ self-hostable, no restrictions

- **fully open source** - permissive for commercial use, see [LICENSE](LICENSE)
- **rebrand-friendly** - swap logos and colors, make it yours
- **complete data control** - all data stays in your infrastructure

---

## 🚀 quickstart

clone the repo and use the production-ready compose file in `.docker/`:

```bash
git clone https://github.com/nokodo-labs/os1.git
cd os1/.docker
docker compose up -d
```

open `http://localhost:888` for the main app or `http://localhost:8383` for the admin console.

> before going live, update `NOKODO__SECURITY__SECRET_KEY` to a long random string and set `NOKODO__SECURITY__CORS_ORIGINS`, `NOKODO__BRANDING__PUBLIC_FRONTEND_ORIGIN`, and `API_ORIGIN` to your actual domain URLs. see [`.docker/docker-compose.yml`](.docker/docker-compose.yml) for all available options.

for environment variable reference, building from source, and development setup see [docs/setup.md](docs/setup.md).

---

## 🗺️ roadmap

see [ROADMAP.md](ROADMAP.md) for planned features and release milestones.

## 🤝 contributing

contributions are welcome! see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 license

OS1 is open-source under a permissive attribution license built on AGPL-3.0 with
additional permissions that allow commercial and closed-source use. See
[LICENSE](LICENSE) for details.

---

<details>
<summary>tech stack</summary>

| layer        | technologies                                                   |
| ------------ | -------------------------------------------------------------- |
| **backend**  | FastAPI, Python 3.13+, SQLAlchemy 2.0+, PostgreSQL 17, Alembic |
| **frontend** | Svelte 5, Vite, Vercel Streamdown, Tailwind 4, TypeScript      |
| **console**  | Svelte 5, Vite, shadcn-svelte, Tailwind 4, TypeScript          |
| **infra**    | Docker Compose, Nginx, GitHub Actions, custom release tooling  |

</details>
