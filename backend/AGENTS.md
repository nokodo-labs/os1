# nokodo AI backend guidelines

## code style

- Python 3.13+ features, type hints everywhere
- SQLAlchemy 2.0+ `Mapped` annotations
- Pydantic v2.11+ for validation
- tabs, unix line endings
- Ruff for linting/formatting/imports
- pytest for testing with fixtures and coverage
- adhere to `nokodo` brand rule of **no auto-capitalization** in comments, docstrings, logging, or any user-facing text. only proper nouns, acronyms and other intentional capitalizations are allowed.

> **reminder** - CLEAN code means:
>
> 1.  NO type ignore / noqa comments. if you NEED to use it, you are probably typing something wrong.
> 2.  NO overuse of comments everywhere. comments are good, but only to explain complex or crucial blocks.
> 3.  NO pragma nocs to skip tests. if you need to skip a test, update the test to cover the case, or remove unreachable code instead.
> 4.  NO use of getattr/setattr/delattr unless it's the only way. it defeats type checkers and is ugly.
> 5.  AVOID direct cast() usage. use only when it's the only way.
> 6.  AVOID use of Any type. only use when absolutely necessary.
> 7.  patterns 1, 4, 5 and 6 can be used to **bypass typing issues**, which is **strictly forbidden**.

## backend codebase map

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
├── nokodo_ai/              # SDK - publishable, standalone execution library
│   ├── adapters/           # provider adapters (openai/anthropic/ollama) + capability ABCs
│   ├── agent.py            # Agent orchestrator (LLM + Tools)
│   ├── llm.py              # LLM high-level interface
│   ├── embedding.py        # EmbeddingModel high-level interface
│   ├── vectorstore.py      # Vectorstore high-level interface
│   ├── tool.py             # Tool decorator / Tool class
│   ├── thread.py           # execution-focused Thread domain model
│   ├── message.py          # execution-focused Message domain models
│   └── tests/              # SDK unit tests
└── tests/                  # E2E integration tests
```

## patterns

- SDK separation: `api/` imports from `nokodo_ai/`, not vice versa
- REST conventions, proper HTTP codes
- validate inputs (Pydantic)
- type everything
- three-tier testing: API tests, SDK tests, E2E tests
- API changes: update backend → run the VS Code tasks `Frontend: Generate API` / `Console: Generate API`

## running backend code

### to run backend:

- always remember to cd into `backend/`
- check the current working directory if unsure where you are.
- always use `uv run` to run backend commands.

### to run tests:

the best way to run all tests is by using the VS Code Task `Backend: Run Tests`. This will show you coverage gaps and any warnings and errors.

to run backend tests manually instead:

1.  follow the steps in `to run backend` above to ensure correct environment setup.
2.  run `uv run pytest` from within the `backend/` directory.

## database migrations

migrations are handled by Alembic and are located in `backend/api/migrations`.
the backend is configured to **automatically run `uv run alembic upgrade head` on startup** using the same configuration the CLI uses.

- **manual**: you can still run Alembic manually if needed:
    ```bash
    cd backend
    alembic -c api/migrations/alembic.ini upgrade head
    ```
