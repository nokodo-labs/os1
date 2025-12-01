# nokodo AI backend guidelines

## Tech stack

-   **Backend**: FastAPI (Python 3.13+), Pydantic AI, SQLAlchemy 2.0+, PostgreSQL 17
-   **Frontend**: Svelte 5, TypeScript, Vite, Vercel AI SDK, shadcn-svelte, TailwindCSS
-   **Type Safety**: OpenAPI TypeScript generator (auto-sync backend → frontend)
-   **Infra**: Docker Compose, Nginx for static builds

## Code style

-   Python 3.13+ features, type hints everywhere
-   SQLAlchemy 2.0+ `Mapped` annotations
-   Pydantic v2.11+ for validation
-   Tabs, unix line endings
-   Ruff for linting/formatting/imports
-   pytest for testing with fixtures and coverage
-   adhere to `nokodo` brand rule of **no auto-capitalization** in comments, docstrings, logging, or any user-facing text. only proper nouns, acronyms and other intentional capitalizations are allowed.

> **Reminder** - CLEAN code means:
>
> -   NO type ignore comments. If you NEED to use it, you are probably typing something wrong.
> -   NO overuse of comments everywhere. Comments are good, but only to explain complex or crucial blocks.
> -   NO pragma nocs to skip tests. If you need to skip a test, update the test to cover the case, or remove unreachable code instead.
> -   NO use of getattr/setattr/delattr unless it's the only way. It defeats type checkers and is ugly.

## Backend codebase map

```
backend/
├── api/                    # FastAPI app
│   ├── v1/                 # API version 1
│   │   ├── routers/        # Route handlers
│   │   ├── service/	    # v1 service layer
│   │   ├── router.py       # v1 router
│   │   └── schemas/        # DTOs for v1-specific routes
│   ├── core/               # Config, database
│   ├── clients/            # External API clients
│   │   ├── redis.py        # Redis client
│   │   ├── smtp.py         # SMTP email client
│   │   └── taskiq.py	    # Taskiq client
│   ├── tasks/              # Background tasks
│   ├── models/             # SQLAlchemy models. These are ORM as well as Domain Models.
│   ├── schemas/            # Common Pydantic schema DTOs across API versions
│   ├── migrations/         # Alembic setup & migrations
│   └── tests/              # API & ORM tests
├── nokodo_ai/              # SDK - fully independent service layer
│   └── tests/              # SDK unit tests
└── tests/                  # E2E integration tests
```

## Patterns

-   SDK separation: `api/` imports from `nokodo_ai/`, not vice versa
-   REST conventions, proper HTTP codes
-   Validate inputs (Pydantic)
-   Type everything
-   Three-tier testing: API tests, SDK tests, E2E tests
-   API changes: Update backend → run `npm run generate:api-types` → types sync

## Running backend code

### **About dev servers**:

-   Always assume the user is already running a dev server with hot reload.
-   Always assume the user is monitoring changes live.
-   Never manually run dev servers like `uvicorn` or `npm run dev` yourself - unless explicitly asked.

### To run backend:

-   Always remember to cd into `backend/`
-   Always enable the virtual environment with `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows).
-   Check the current working directory if unsure where you are.
-   Check terminal output if unsure whether the venv is activated. It should be prefixed with `(.venv)`.

### To run tests:

The simplest way to run all tests is by using the VSCode Task `Backend: Run all tests`.

To run backend tests manually instead:

1.  Follow the steps in `To run backend` above to ensure correct environment setup.
2.  Run `pytest` from within the `backend/` directory.
