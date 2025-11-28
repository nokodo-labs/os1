# nokodo AI plan

> _clean, simple, powerful - built for the future of AI interaction_ ✨

---

## 🛠️ tech stack

### frontend

-   **svelte 5** — fully static build served via **nginx**
-   **vercel AI SDK** (latest) for AI integration
-   **shadcn-svelte** component library
    -   built on **Bits UI** primitives
    -   tailwind-based, copy-paste components

### backend

-   **FastAPI** framework
-   **pydantic** for data validation
-   **pydantic AI** (new version) for agent orchestration

### architecture

-   **monorepo** structure for unified codebase management
-   **admin UI** — separately hosted on different port

### design system

-   **liquid glass aesthetic** — custom implementations
    -   CSS `backdrop-filter` + gradients
    -   SVG filters for metallic paint effects
    -   Motion One for physics-based animations
-   **design inspiration** — reactbits.dev patterns adapted for svelte

---

## 🎨 UI/UX philosophy

-   **super modern aesthetic** — apple-inspired liquid glass elements
-   **dynamic & interactive** — physics-based animations
-   **reactive UX** — real-time state updates and smooth transitions
-   emphasis on fluidity and premium feel
-   **never expose internal workings** on frontend — keep UI clean
-   **never expose model details** to end users

---

## 🤖 AI agents

-   **curated selection** — only a few high-quality agents
-   **zero setup required** — works out of the box
-   **multi-functional** — each agent handles diverse tasks

**model & agent architecture:**

> models fetch directly from APIs containing foundation models;  
> agents are user-facing abstractions with tools and prompting

---

## 🔥 agentic coding (killer feature)

**heavy AI agentic coding support** baked directly into the platform

### asynchronous autonomous coding agent

-   full sandbox environment with terminal access
-   iterative code changes, testing, and refinement
-   automatic PR creation when complete
-   see **copilot coding sessions** under async task system for details

---

## 🧠 memory system

> ⚠️ **memory system is critical** — must be highly accurate and reliable

### core functionality

-   **high accuracy relevant memory detection** — intelligent context matching
-   **asynchronous memory manager** — detects, updates, and deletes memory intelligently
-   reuse logic from OWUI extension auto-memory functionality

### implementation options

-   [ ] evaluate **mem0.ai** for intelligent memory management
    -   ⚠️ closed source, API-only access
    -   test token: `m0-S67dQyPWc6AHmSYqzshXFh2zW7AKCUzbnxjHedZx`
-   [ ] evaluate if benefits outweigh closed-source limitations
-   [ ] compare with open-source alternatives
-   [ ] **alternative approach** (if not using mem0):
    -   select great embedding model
    -   design robust data modeling
    -   tune retrieval process for optimal accuracy

### chat recall system

-   **efficient chat retrieval** — fetch relevant OR recent chats, inject select info into context
-   **initial implementation:** simple "top 3 most recent chats"
-   **future enhancement:** relevance scoring + context-aware selection

---

## 🧰 built-in tools & capabilities

### intelligence router

-   [ ] **smart model selection system**
    -   instantly detects required intelligence level for each query
    -   automatically deploys appropriate LLM (cheap vs expensive)
    -   **goal:** use cheaper models for simple queries → significant cost savings
    -   transparent to users — they just get great responses
    -   factors: query complexity, context requirements, tool needs

### core tools

| tool                 | description                                                          |
| -------------------- | -------------------------------------------------------------------- |
| **web search**       | tiered: basic (fast) + agentic (perplexity-powered, complex queries) |
| **webpage fetch**    | scrape and parse web content                                         |
| **memory add**       | store contextual information                                         |
| **fetch from chats** | retrieve conversation history                                        |
| **media generation** | image & video creation/editing                                       |
| **python executor**  | sandboxed code execution + file creation                             |

-   [ ] implement tiered web search (basic vs agentic)
    -   AI knows when it's agentic → asks complex, comprehensive queries
    -   optimizes for 1 big query vs multiple small ones → cost savings
-   [ ] enable native file creation via python code interpreter
-   [ ] return download links for user-created files

### content handling

-   **native artifacts support** — render and interact with generated content
-   **native file retrieval** — access and process uploaded files
-   **native file creation/editing** — modify files via built-in tools

---

## 👤 user management

-   [ ] implement **OIDC** (OpenID Connect) authentication
    -   modern, future-proof implementation from day one
    -   start with custom OIDC providers (self-hosted, enterprise)
    -   later expand to standard providers (Google, Apple, etc.)
-   [ ] support **federated users and groups**
-   [ ] **user groups** — let users band together and consolidate resource access
    -   shared threads, files, projects among group members
    -   group-level quotas and permissions
-   [ ] **user roles** (admin-managed, invisible to users)
    -   manage permissions and access control
    -   subscription plans and tiers (if applicable)
    -   role-based feature gating
-   [ ] customizable user profiles with key settings

---

## 🚦 rate limiting & usage control

-   [ ] implement **native limiter system**
    -   support multiple limit types: tokens, characters, cost
    -   granular controls: per user, global, per minute, per hour, custom periods
-   [ ] **clear error messaging** when limits exceeded
    -   format: _"you have used your allowed [x], your limit resets at [time]"_

---

## 🔔 notification system

-   [ ] **multi-backend notification support**
    -   **phase 1:** simple PWA service worker
    -   **phase 2:** SMTP for email notifications
    -   **future phases:** telegram, additional channels
-   [ ] **SMTP support**
    -   email notifications for important events
    -   task completion alerts
    -   user messaging notifications
    -   configurable per-user email preferences

---

## ⚡ asynchronous task system

> generic multi-turn agentic session framework

-   supports any long-running AI task with multiple iterations
-   AI can iterate — decides when task is complete
-   produces custom output (document, results, artifacts, etc.)

### session types

#### 🔥 copilot coding sessions (killer feature)

> **unique selling point** — no competitor offers this level of autonomy in OSS

1. user provides task/feature request
2. spawns isolated sandbox environment (Docker/Coder integration)
3. clones repository into sandbox
4. full capabilities: terminal access, code changes, tool usage, web access
5. iterative workflow: read code → make changes → run tests → refine
6. continues until goal achieved
7. pushes to GitHub as new branch + creates PR

**implementation notes:**

-   GitHub SSO for authorization
-   leverage GitHub Copilot Chat open source codebase
-   multi-model support with extensive customization

#### 🔍 deep research sessions

-   takes several minutes to complete
-   AI performs multiple search iterations
-   builds comprehensive final document
-   sends notification when complete

#### other session types

-   **creative projects** — multi-step generation with refinement
-   **data analysis** — fetch → process → visualize workflows

### architecture

-   each session type has custom result format
-   each session type can define custom UI for display
-   notification on completion
-   progress tracking and intermediate updates

---

## 🗺️ future roadmap

### extensibility

-   [ ] custom community-made tools
-   [ ] custom models integration
-   [ ] custom filters

### UI/UX architecture

-   [ ] **top header/island** — persistent UI anchor
    -   always-present element (like Windows taskbar or macOS menu bar)
    -   ties together all pages and apps
    -   adapts content dynamically based on current view
    -   central navigation and quick actions hub
-   [ ] **design team need** — dedicated UI designer
    -   liquid glass/mercury aesthetic requires specialized skills
    -   consistent design language across all components
    -   focus engineering time on functionality

### user messaging

-   [ ] **direct messaging / chat** — AI-enhanced communication
    -   WhatsApp/iMessage-style user-to-user messaging
    -   add people AND AIs to the same conversation
    -   AI can assist, summarize, translate in real-time
    -   group chats with mixed human/AI participants

### reminders

-   [ ] **reminders app** — AI-enhanced timed reminders
    -   natural language reminder creation
    -   integration with Google/Apple calendar ecosystems
    -   smart reminder suggestions from context
    -   notification delivery via preferred channels

### projects

-   [ ] directories to aggregate and organize content
    -   group related threads, files, and resources
    -   project-level settings and sharing
    -   cross-project search and navigation
    -   collaborative access (via user groups)

---

## 🌐 "everything app" vision

> become the main point of access to your computer and phone

### productivity features

-   notes
-   reminders
-   calendar integrations

### external integrations

-   smart home links
-   Spotify integration
-   homelab setup connections
-   movie requests (Plex/Jellyfin)

### universal access point

-   phone launcher — type app names, AI-suggested apps to open
-   calendar, alarms, reminders integration
-   music control and recommendations
-   phone contacts and communications
-   email management and triage
-   **infinite extensibility** — integrate with anything via plugins
