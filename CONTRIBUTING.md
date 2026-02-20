# contributing to nokodo

thank you for your interest in contributing! this guide covers everything you need to get started.

## getting started

1. fork the repository
2. clone your fork locally
3. follow the [setup guide](docs/setup.md) to get your environment running
4. create a feature branch from `dev`

## development workflow

### branch naming

use conventional commit style for branch names:

```
feat/frontend/add-chat-component
fix/backend/auth-token-refresh
docs/update-readme
```

### commit messages

use [conventional commits](https://www.conventionalcommits.org/):

```
feat(frontend): add new chat component
fix(backend): resolve auth token refresh issue
docs: update setup instructions
refactor(api): simplify user router
```

**breaking changes** should be marked with `!`:

```
feat!: change API response format
```

### pull requests

1. target the `dev` branch
2. use conventional commit format for the PR title
3. fill out the PR template completely
4. ensure all checks pass before requesting review

## code style

### python (backend)

- python 3.13+ features and type hints everywhere
- SQLAlchemy 2.0+ with `Mapped` annotations
- Pydantic v2.11+ for validation
- tabs for indentation, unix line endings
- Ruff for formatting and linting
- no `type: ignore` or `noqa` comments - fix the actual issue
- no `Any` type unless absolutely necessary
- no `cast()` unless it's the only way

**run checks:**

```bash
cd backend
uv run ruff format .
uv run ruff check . --fix
uv run pytest -v
```

### typescript/svelte (frontend & console)

- TypeScript strict mode
- Svelte 5 runes only
- Tailwind 4 for styling
- tabs for indentation, single quotes, no semicolons
- Prettier for formatting, ESLint for linting
- no `@ts-ignore` or `@ts-nocheck` - fix the actual issue
- no `any` type unless absolutely necessary
- no `as Type` assertions unless it's the only way

**run checks:**

```bash
cd frontend  # or console
pnpm run format
pnpm run lint
pnpm run check
pnpm run test
```

### brand style

nokodo uses **lowercase typography** throughout. only use uppercase for:

- acronyms (API, URL, etc.)
- proper nouns
- intentional emphasis

this applies to comments, docstrings, logging, and user-facing text.

### comments and section headers

- avoid decorative separator comments (e.g., long repeated dashes or banner lines).
- keep section headers as short, plain comment lines.

## testing

### backend

```bash
cd backend
uv run pytest -v                           # all tests
uv run pytest api/tests/ -v                # API tests only
uv run pytest nokodo_ai/tests/ -v          # SDK tests only
uv run pytest --cov=api --cov=nokodo_ai    # with coverage
```

### frontend

```bash
cd frontend
pnpm run test                               # run tests
pnpm run test:coverage                      # with coverage
```

### console

```bash
cd console
pnpm run check                              # type check
pnpm run lint                               # lint
```

## API changes

when you modify backend API endpoints:

1. make your changes in the backend
2. ensure the backend is running (`uv run uvicorn api.main:app --reload`)
3. regenerate TypeScript types using VS Code tasks:
    - **Frontend: Generate API Types**
    - **Console: Generate API**

## project structure

| directory   | purpose                                    |
| ----------- | ------------------------------------------ |
| `backend/`  | FastAPI app + nokodo_ai SDK                |
| `frontend/` | user-facing Svelte app                     |
| `console/`  | admin console (separate Svelte app)        |
| `docs/`     | project documentation                      |
| `.docker/`  | docker configs and compose files           |
| `.github/`  | CI/CD, templates, workflows                |
| `.vscode/`  | editor config, tasks, debug configurations |

## questions?

open an issue or start a discussion. we're happy to help!
