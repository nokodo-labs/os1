# nokodo AI backend guidelines

## code style

- Python 3.14+ features, type hints everywhere
- SQLAlchemy 2.0+ `Mapped` annotations
- Pydantic v2.11+ for validation
- tabs, unix line endings
- Ruff for linting/formatting/imports
- ty for type checking
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
> 7.  AVOID lazy imports. they can hide circular dependencies. only use when strictly NEEDED, and no other architectural changes can be made to avoid them.
> 8.  patterns 1, 4, 5 and 6 can be used to **bypass typing issues**, which is **strictly forbidden**.

## backend codebase map

```
backend/
├── api/                         # FastAPI backend app
│   ├── main.py                  # app entrypoint and startup wiring
│   ├── boot_settings.py         # early boot settings (loaded before full settings)
│   ├── permissions.py           # permission enums + DefaultPermissions (shared by models/settings)
│   ├── local_tasks.py           # in-process fire-and-forget asyncio task helpers
│   ├── taskiq.py                # TaskIQ broker startup/shutdown wiring
│   ├── ...                      # exceptions, logging, openapi, runtime, constants, external API clients
│   ├── database/                # DB engine init, async session, search cursor helpers
│   ├── middleware/              # rate limiting, request id, logging, api version, security headers
│   ├── migrations/              # Alembic config and migration scripts
│   ├── models/                  # SQLAlchemy ORM models (one file per entity)
│   ├── redis/                   # Redis client, pub/sub, cache, cache invalidation
│   ├── routers/                 # top-level/system routers
│   ├── schemas/                 # shared Pydantic schemas and API DTOs (one file per domain)
│   ├── service/                 # app-level services (pwa_manifest, web_assets)
│   ├── settings/                # settings models + DB/env loading
│   ├── storage/                 # storage backends (local/s3)
│   ├── tasks/                   # top-level TaskIQ task registry
│   ├── tests/                   # API/service/unit coverage for backend package
│   └── v1/                      # versioned API composition
│       ├── router.py            # v1 router mount
│       ├── routers/             # v1 route handlers (one file per domain)
│       │   └── integrations/    # integration routers (mcp, open_webui)
│       ├── schemas/             # v1-only schemas (auth, settings, web_search)
│       ├── service/             # v1 service layer
│       │   ├── chat/            # AI chat orchestration
│       │   │   ├── models.py    # chat model resolution + JSON schema calls
│       │   │   ├── tools/       # chat tool implementations + registry
│       │   │   ├── hooks/       # post-execution hooks (memory post-processing)
│       │   │   ├── filters/     # pre-execution filters (context, attachments, citations, memory, steering, etc.)
│       │   │   ├── context_compaction/  # context budgets, pruning, summarization, tool i/o trimming
│       │   │   └── ...          # agents, context, steering, messages, message_metadata/references,
│       │   ├── runs/            # run lifecycle, output, steering, cross-worker routing, access reconciliation
│       │   ├── threads/         # thread CRUD (core), messages, participants, summaries, search, maintenance
│       │   ├── calendar/        # calendars, events, recurrence, search, cache
│       │   ├── reminders/       # reminder CRUD (core), lists, search, cache
│       │   ├── scheduling/      # recurrence rule helpers
│       │   ├── web_search/      # agentic web search, loaders, progress tracking
│       │   ├── media/           # media generation (images, video, audio)
│       │   ├── files/           # file processing, vectorization, modalities, search, message links
│       │   ├── prompts/         # prompt CRUD (core/service), runtime, external, cache
│       │   ├── search/          # cross-resource search aggregator, grouping, primitives
│       │   ├── social/          # friendship, privacy, visibility helpers
│       │   ├── authorization/   # access-rule resolution, inheritance, predicates, cache
│       │   ├── integrations/    # third-party integration services (mcp/, open_webui/)
│       │   ├── event_bus.py     # cross-process WebSocket fanout relay (Redis pub/sub)
│       │   ├── task_bus.py      # cross-worker task SSE bus (Redis pub/sub)
│       │   ├── collaborative_documents.py  # CRDT-based collaborative doc editing
│       │   ├── document_sessions.py        # collaborative document session tracking
│       │   ├── listing.py       # shared list-endpoint filtering + sorting helpers
│       │   ├── resource_payload_cache.py   # per-resource Redis payload cache
│       │   └── ...              # access_rules, agents, auth, blocks, embeddings, events, friends,
│       │                        #   groups, memories, models, notes, notifications, plugins, projects,
│       │                        #   providers, roles, runs, scheduled_items, settings, tasks, users,
│       │                        #   user_activity, user_clients, vectorize, vectorstores, web_push
│       └── tasks/               # v1 TaskIQ task modules (calendar, reminders, threads, files, open_webui)
├── nokodo_ai/                   # standalone SDK/runtime library
│   ├── adapters/                # provider adapters + base/ (openai, anthropic, google, ollama, qdrant,
│   │                            #   voyageai, markitdown, nokodo_ai)
│   ├── agents.py                # agent orchestration
│   ├── chat_models.py           # chat model abstractions
│   ├── messages.py              # message domain primitives
│   ├── threads.py               # thread domain primitives
│   ├── tool.py                  # tool interfaces/decorators
│   ├── filters.py               # filter pipeline interfaces
│   ├── hooks.py                 # hook pipeline interfaces
│   ├── deltas.py                # streaming delta primitives
│   ├── ...                      # audio/image/video models, embeddings, chunkers, loaders,
│   │                            #   vectorstores, context, token_estimation
│   ├── types/                   # SDK type helpers
│   ├── utils/                   # SDK utilities (typeid, sse, tokens, security, vectors, etc.)
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

pytest natively rejects overlapping controller sessions in the same checkout via `tests/session_lock.py`; xdist workers remain allowed. run pytest normally without a separate process check or external lock.

### to run type checks:

- run `uv run ty check . ../tools/autogen-migration.py ../tools/export-openapi.py` from within the `backend/` directory.

## database migrations

migrations live in `backend/api/migrations`; applied automatically on startup.

to create a new migration, use the **`backend: autogen migration` VS Code task** or:

```bash
uv run python tools/autogen-migration.py --message "description"
```

creates a temp DB, upgrades to `head`, autogenerates against the model diff, saves to `temp/alembic-autogen/`. review, edit, move to `backend/api/migrations/versions/`.
to check for drift without generating a file, use `--check`, no message needed.

never run bare `alembic revision --autogenerate` against the live dev DB - local drift causes false positives.

## M2M relationships

- **ORM**: default lazy (no extra queries) + a read-only `_ids` property. expose IDs, not objects.
- **service**: `selectinload()` only in queries whose results are serialized to API responses. internal/background paths skip it.
