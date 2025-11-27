# nokodo AI plan

## tech stack

### frontend

-   **svelte 5** - fully static build
-   served via **nginx**
-   integrate **vercel AI SDK** (latest version)

### backend

-   **FastAPI** framework
-   **pydantic** for data validation
-   **pydantic AI** (new version) for AI agent orchestration

### architecture

-   **monorepo** structure for unified codebase management
-   **admin UI** - separately hosted on different port

### UI components & styling

-   **shadcn-svelte** - beautiful, accessible component library
    -   built on **Bits UI** primitives
    -   tailwind-based, copy-paste components
-   **liquid glass aesthetic** - custom implementations
    -   CSS backdrop-filter + gradients
    -   SVG filters for metallic paint effects
    -   Motion One for physics-based animations
-   **design inspiration** - reactbits.dev patterns adapted for Svelte

## core features & ux

### AI agentic coding

-   **heavy AI agentic coding support** baked directly into the platform
-   seamless developer experience with intelligent code assistance
-   **asynchronous autonomous coding agent** - unique killer feature
    -   full sandbox environment with terminal access
    -   iterative code changes, testing, and refinement
    -   automatic PR creation when complete
    -   see "copilot coding sessions" under async task system for details

### UI/UX design philosophy

-   **super modern aesthetic** - apple-inspired liquid glass elements
-   **dynamic & interactive** - physics-based animations
-   **reactive UX** - real-time state updates and smooth transitions
-   emphasis on fluidity and premium feel

### AI agents

-   **curated selection** - only a couple of high-quality agents
-   **zero setup required** - works out of the box
-   **multi-functional** - each agent handles diverse tasks
-   **model & agent architecture** - models fetch directly from APIs containing foundation models, agents are user-facing abstractions with tools and prompting

### user management

-   [ ] implement **OIDC** (OpenID Connect) authentication

-   [ ] support **federated users and groups**

-   [ ] customizable user profiles with key settings

### privacy & security

-   **never expose internal workings** on the frontend - keep UI clean and user-friendly
-   **never expose model details** to end users

## built-in tools & capabilities

### core tools

-   [ ] **web search** - internet information retrieval

-   [ ] **webpage fetch** - scrape and parse web content

-   [ ] **memory add** - store contextual information

-   [ ] **fetch from chats** - retrieve conversation history

-   [ ] **image & video creation/editing** - generative media tools

-   [ ] **python code execution** - run code in sandboxed environment

-   [ ] enable native file creation via python code interpreter

-   [ ] return download links for user-created files

### content handling

-   **native artifacts support** - render and interact with generated content
-   **native file retrieval** - access and process uploaded files
-   **native file creation/editing** - modify files via built-in tools

## memory system

### core memory functionality

-   **memory system is critical** - must be highly accurate and reliable
-   **high accuracy relevant memory detection** - intelligent context matching
-   **asynchronous memory manager** - detects, updates, and deletes memory intelligently
-   **reuse logic from OWUI extension** auto-memory functionality

### memory implementation options

-   [ ] evaluate **mem0.ai** for intelligent memory management

*   **note**: closed source, API-only access
*   **test token**: `m0-S67dQyPWc6AHmSYqzshXFh2zW7AKCUzbnxjHedZx`

-   [ ] evaluate if benefits outweigh closed-source limitations

-   [ ] compare with open-source alternatives

-   [ ] **alternative approach** (if not using mem0):

*   select great embedding model
*   design robust data modeling
*   tune retrieval process for optimal accuracy

### chat recall system

-   **efficient chat retrieval** - fetch relevant OR recent chats and inject select info into context
-   **initial implementation**: simple "top 3 most recent chats"
-   **future enhancement**: improve with relevance scoring and context-aware selection

## rate limiting & usage control

-   [ ] implement **native limiter system**

*   support multiple limit types: tokens, characters, cost
*   granular controls: per user, global, per minute, per hour, custom periods

-   [ ] **clear error messaging** when limits exceeded

*   format: "you have used your allowed [x], your limit resets at [time]"
*   user-friendly and transparent

## notification & task systems

### notification system

-   [ ] **multi-backend notification support**

*   **phase 1**: simple PWA service worker
*   **future phases**: email, telegram, additional channels

### asynchronous task system

-   [ ] **generic multi-turn agentic session framework**
    -   supports any long-running AI task with multiple iterations
    -   AI can iterate - decides when task is complete
    -   produces custom output (document, results, artifacts, etc.)

**session types:**

-   **copilot coding sessions** - autonomous code development (🔥 KILLER FEATURE)
    -   user provides task/feature request
    -   spawns isolated sandbox environment (Docker/Coder integration)
    -   clones repository into sandbox
    -   full capabilities: terminal access, code changes, tool usage, web access
    -   iterative workflow: read code → make changes → run tests → refine
    -   continues until goal achieved
    -   pushes to GitHub as new branch + creates PR
    -   GitHub SSO for authorization
    -   leverage GitHub Copilot Chat open source codebase
    -   multi-model support with extensive customization
    -   **unique selling point** - no competitor offers this level of autonomy in OSS
-   deep research - multi-turn web search → comprehensive document
-   creative projects - multi-step generation with refinement
-   data analysis - fetch → process → visualize workflows

**architecture:**

-   each session type has custom result format
-   each session type can define custom UI for display
-   notification on completion
-   progress tracking and intermediate updates

## future expansion & roadmap

### deep research capability

-   [ ] **asynchronous research sessions** - first implementation of multi-turn framework
    -   takes several minutes to complete
    -   AI performs multiple search iterations
    -   builds comprehensive final document
    -   sends notification when complete

### extensibility

-   [ ] **custom community-made tools**

-   [ ] **custom models integration**

-   [ ] **custom filters**

### "everything app" vision

-   **productivity features**
    -   notes
    -   reminders
    -   calendar integrations
-   **external integrations**
    -   smart home links
    -   Spotify integration
    -   homelab setup connections
    -   movie requests (e.g., Plex/Jellyfin)
-   **universal access point**
    -   become the main point of access to your computer and phone
    -   phone launcher - type app names, AI-suggested apps to open
    -   calendar, alarms, reminders integration
    -   music control and recommendations
    -   phone contacts and communications
    -   email management and triage
    -   **infinite extensibility** - integrate with anything via plugins

---

_clean, simple, powerful - built for the future of AI interaction_ ✨
