# nokodo AI

AI platform with agentic coding support, beautiful UI, and comprehensive tooling.

## Stack

-   **Backend**: FastAPI (Python 3.13+), Pydantic AI, SQLAlchemy 2.0+, PostgreSQL 17
-   **Frontend**: Svelte 5, TypeScript, Vite, Vercel AI SDK, shadcn-svelte, TailwindCSS
-   **Type Safety**: OpenAPI TypeScript generator (auto-sync backend → frontend)
-   **Infra**: Docker Compose, Nginx for static builds

## Code Style

### Python

-   Python 3.13+ features, type hints everywhere
-   SQLAlchemy 2.0+ `Mapped` annotations
-   Pydantic v2.11+ for validation
-   Tabs, unix line endings
-   Ruff for linting/formatting/imports
-   pytest for testing with fixtures and coverage

> **Reminder** - CLEAN code means:
>
> -   NO type ignore comments. If you NEED to use it, you are probably typing something wrong.
> -   NO over use of comments everywhere. Comments are good, but only to explain key, complex or crucial blocks.

### TypeScript/Svelte

-   TypeScript strict mode
-   Svelte 5 runes only
-   shadcn-svelte components with Bits UI primitives
-   TailwindCSS for styling
-   Vercel AI SDK for AI interactions
-   OpenAPI-generated types for type safety
-   Tabs, unix line endings

## UI/UX Philosophy

-   **Liquid UI**: A next-gen aesthetic with liquid elements, unifying Apple-inspired liquid glass with an unique Mercury-like liquid metal effect
-   **Physics-based Animations**: Motion One for smooth, realistic interactions
-   **Modern & Premium**: Apple-inspired, fluid, reactive real-time updates
-   **Component Library**: shadcn-svelte built on Bits UI primitives

## Codebase map

```
backend/
├── api/                    # FastAPI app (routes, ORM, DB)
│   ├── v1/endpoints/       # Route handlers
│   ├── core/               # Config, database
│   ├── models/             # SQLAlchemy models
│   ├── schemas/            # Pydantic schemas
│   └── tests/              # API & ORM tests
├── nokodo_ai/              # SDK/service layer
│   └── tests/              # SDK unit tests
└── tests/                  # E2E integration tests

frontend/src/
├── lib/
│   ├── api/                # Type-safe API client
│   └── [components]        # Svelte components
├── main.ts                 # Entry
├── App.svelte              # Main Svelte app
└── app.css                 # Global styles (TailwindCSS)
```

## Patterns

-   SDK separation: `api/` imports from `nokodo_ai/`, not vice versa
-   REST conventions, proper HTTP codes
-   Validate inputs (Pydantic)
-   Type everything
-   Three-tier testing: API tests, SDK tests, E2E tests
-   API changes: Update backend → run `npm run generate:api-types` → types sync

## AI Agent Behavior

### General Guidelines

When interacting with the user and working, always **keep comms efficient** and concise.

As an AI, your context is limited, thus overly verbose responses will directly affect how your performance degrades over time.
**Less is more** - focus on addressing the user's needs never create extra files or documentation to report changes unless explicitly asked.

### Plan and Reflect

Before executing any tasks, follow this process:

1. **Read** the user's request carefully.
2. **Fetch and read** any relevant files, documentation, or context.
3. **Think and plan** your approach step-by-step. Use the TODOs tool to stay grounded as you iterate.

Skipping any of these steps will lead to increased costs and suboptimal results.

### Running Code

**About dev servers**:

-   Always assume the user is already running a dev server with hot reload.
-   Always assume the user is monitoring changes live.
-   Never manually run dev servers like `uvicorn` or `npm run dev` yourself - unless explicitly asked.
-   If you want feedback on changes, simply ask the user what they see!

When you _do_ want to run code, always:

-   **Backend**: Always remember to cd into `backend/`. Always enable the virtual environment, otherwise your code won't run.
-   **Frontend**: Always remember to cd into `frontend/`.
-   Check the current working directory if unsure where you are.
-   Check terminal output if unsure whether the venv is activated.
