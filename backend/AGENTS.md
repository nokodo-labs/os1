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
├── api/                         # FastAPI backend app
│   ├── main.py                  # app entrypoint and startup wiring
│   ├── exceptions.py            # exception handlers
│   ├── logging.py               # logging configuration and utilities
│   ├── openapi.py               # OpenAPI response defaults
│   ├── runtime.py               # event loop and runtime configuration
│   ├── tasks.py                 # shared background task utilities
│   ├── ...                      # perplexity, tavily, searxng API clients, etc.
│   ├── database/                # DB init and search cursor helpers
│   ├── middleware/              # API versioning, request id, logging, headers
│   ├── migrations/              # Alembic config and migration scripts
│   ├── models/                  # SQLAlchemy ORM models
│   ├── routers/                 # top-level/system routers
│   ├── schemas/                 # shared Pydantic schemas and API DTOs
│   ├── settings/                # settings models and DB/env loading
│   ├── storage/                 # storage backends (local/s3)
│   ├── tests/                   # API/service/unit coverage for backend package
│   └── v1/                      # versioned API composition
│       ├── app.py               # v1 app setup
│       ├── router.py            # v1 router mount
│       ├── routers/             # v1 route handlers
│       ├── schemas/             # v1-only schemas
│       ├── service/             # v1 service layer (auth/chat/files/etc.)
│       │   ├── chat/            # ai chat orchestration
│       │   │   ├── tools/       # chat tool implementations + registry
│       │   │   ├── hooks/       # post-execution hooks + registry
│       │   │   ├── filters/     # pre-execution filters (context injection)
│       │   │   └── models.py    # chat model resolution + JSON schema calls
│       │   ├── web_search/      # agentic web search + web loaders
│       │   ├── media/           # media generation (images, video, audio)
│       │   └── ...              # auth, files, memories, threads, etc.
│       └── tasks/               # v1 async/background task modules
├── nokodo_ai/                   # standalone SDK/runtime library
│   ├── adapters/                # provider adapters + base adapter contracts
│   ├── agents.py                # agent orchestration
│   ├── chat_models.py           # chat model abstractions
│   ├── embeddings.py            # embedding abstractions
│   ├── vectorstores.py          # vectorstore abstractions
│   ├── messages.py              # message domain primitives
│   ├── threads.py               # thread domain primitives
│   ├── tool.py                  # tool interfaces/decorators
│   ├── types/                   # SDK type helpers
│   ├── utils/                   # SDK utility helpers
│   └── tests/                   # SDK unit tests
└── tests/                       # backend integration/e2e-style tests
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

migrations live in `backend/api/migrations`; applied automatically on startup.

to create a new migration, use the **`backend: autogen migration` VS Code task** or:

```bash
uv run --project backend python tools/autogen-migration.py --message "description"
```

creates a temp DB, upgrades to `head`, autogenerates against the model diff, saves to `temp/alembic-autogen/`. review, edit, move to `backend/api/migrations/versions/`.

never run bare `alembic revision --autogenerate` against the live dev DB - local drift causes false positives.

## M2M relationships

- **ORM**: default lazy (no extra queries) + a read-only `_ids` property. expose IDs, not objects.
- **service**: `selectinload()` only in queries whose results are serialized to API responses. internal/background paths skip it.
