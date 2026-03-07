# OS1 roadmap

this document outlines planned features, improvements, and milestones. it is a living document and will change as priorities evolve.

---

## currently in progress

- **native tracking** - token usage per message, cost accounting against model pricing, per-user and per-group spend visibility, activity dashboards in the admin console
- **canvas / artifact library** - file creation and editing in-conversation, centralized artifact management
- **best-in-class RAG** - document upload and querying within conversations and projects, hybrid search with reranking
- **projects** - organize threads, files, and resources into shared workspaces

---

## near-term

- **native iOS and Android apps** - native mobile clients
- **follow-up questions** - AI-generated suggested follow-ups after every response
- **agent run steering** - interrupt, redirect, or inject context into a running agent mid-execution
- **import flows** - one-click import of all user data from Open WebUI, ChatGPT, LibreChat, and LobecChat
- **notifications** - email (SMTP), Telegram, and in-app push notifications
- **prompt library UI** - browse, create, and manage composable Jinja2 prompts from the frontend
- **memory management** - user-facing view to review, edit, and delete stored memories
- **usage dashboard** - per-user and admin views of token usage, costs, and activity over time
- **thread sharing** - share individual conversations with a link or group members

---

## medium-term

- **bring-your-own agents** - app users can define, configure, and share custom agents without admin access
- **agent skills** - composable skill blocks that give agents specialized capabilities
- **adaptive agent personality** - per-user style and tone preferences that agents learn and apply over time
- **custom tool builder** - define and deploy tools visually without touching backend code
- **workflow automation** - multi-step, trigger-based automation built on the agent system
- **model fine-tuning support** - pluggable adapter for fine-tuned model variants
- **expanded media** - audio generation, transcription, and video understanding

---

## longer-term / exploratory

- **plugin and agent marketplace** - discover and install community-built agents, tools, and extensions
- **messaging app** - standalone messaging experience with AI woven in natively
- **Spotify integration** - control and interact with your music via AI
- **Plex and Seer integrations** - browse and manage your media library from within nokodo
- **desktop app** - Electron/Tauri wrapper for tighter OS integration
- **multi-tenant SaaS mode** - org-level isolation for hosted deployments
- **LLM observability** - trace viewer, latency breakdown, and cost analytics per request

---

contributions are welcome. see [CONTRIBUTING.md](CONTRIBUTING.md) to get involved.
