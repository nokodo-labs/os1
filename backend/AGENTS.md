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
> 1.  NO type ignore comments. If you NEED to use it, you are probably typing something wrong.
> 2.  NO overuse of comments everywhere. Comments are good, but only to explain complex or crucial blocks.
> 3.  NO pragma nocs to skip tests. If you need to skip a test, update the test to cover the case, or remove unreachable code instead.
> 4.  NO use of getattr/setattr/delattr unless it's the only way. It defeats type checkers and is ugly.
> 5.  AVOID direct cast() usage. Use only when it's the only way.
> 6.  AVOID use of Any type. Only use when absolutely necessary.
> 7.  Patterns 1, 4, 5 and 6 can be used to **bypass typing issues**, which is **strictly forbidden**.

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

## openapi + codegen

-   keep the backend running at `http://localhost:8000`; use VS Code tasks `Frontend: Generate API (types + client)` and `Console: Generate API (types + client)` to sync consumers directly from the live schema.

## Running backend code

### **About dev servers**:

-   Always assume the user is already running a dev server with hot reload.
-   Always assume the user is monitoring changes live.
-   Never manually run dev servers like `uv run uvicorn` or `npm run dev` yourself - unless explicitly asked.

### To run backend:

-   Always remember to cd into `backend/`
-   Always enable the virtual environment with `source .venv/bin/activate` (Linux/Mac) or `.venv\Scripts\activate` (Windows).
-   Check the current working directory if unsure where you are.

### To run tests:

The best way to run all tests is by using the VSCode Task `Backend: Quick Tests`. This will show you coverage gaps and any warnings and errors.

To run backend tests manually instead:

1.  Follow the steps in `To run backend` above to ensure correct environment setup.
2.  Run `uv run pytest` from within the `backend/` directory.

## Database Migrations

Migrations are handled by Alembic and are located in `backend/api/migrations`.
The backend is configured to **automatically run `uv run alembic upgrade head` on startup** using the same configuration the CLI uses.

-   **Manual**: You can still run Alembic manually if needed:
    ```bash
    cd backend
    alembic -c api/migrations/alembic.ini upgrade head
    ```
