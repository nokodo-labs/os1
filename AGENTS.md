# nokodo AI

AI platform with agentic coding support, beautiful UI, and comprehensive tooling.

## tech stack

- **Backend**: FastAPI (Python 3.13+), SQLAlchemy 2.0+, PostgreSQL 17
- **Frontend**: Svelte 5, TypeScript, Vite, Vercel AI SDK, shadcn-svelte, TailwindCSS
- **Console**: Svelte 5, TypeScript, Vite, shadcn-svelte, TailwindCSS
- **Infra**: Docker Compose, Nginx + static builds, GitHub Actions CI/CD, custom release tooling

## AI agent behavior

### general guidelines

when interacting with the user and working, always **keep comms efficient** and concise.

as an AI, your context is limited, thus overly verbose responses will directly affect how your performance degrades over time.
**less is more** - focus on addressing the user's needs never create extra files or documentation to report changes unless explicitly asked.

never attempt to run dev servers. always assume a dev server with hot reload is running and monitored live by the user.
to test changes, use dedicated check commands or run proper tests instead.

### ascii-only formatting

- use only ASCII in comments/docstrings unless the file already uses non-ASCII and the user asks for it.
- no em/en dashes or box-drawing separators; avoid decorative separators. use short plain comment headers and `-`.

### instruction files

when you want to work on the codebase, you **must ALWAYS** find and read the **closest AGENTS.md file to your target** work area.
find additional AGENTS.md files in each of the 3 main components.
refer to those for component-specific instructions, information, and guidelines:

- backend/AGENTS.md - Backend
- frontend/AGENTS.md - Frontend
- console/AGENTS.md - Console

### plan and reflect

before executing any tasks, follow this process:

1. **read** the user's request carefully.
2. **fetch and read** any relevant files, documentation, or context.
3. **think and plan** your approach step-by-step. use the TODOs tool to stay grounded as you iterate.

skipping any of these steps will lead to increased costs and suboptimal results.

### **about dev servers**:

- always assume the user is already running a dev server with hot reload.
- always assume the user is monitoring changes live.
- never manually run dev servers like `uv run uvicorn` or `npm run dev` yourself - unless explicitly asked.

### validating your work

to validate your work, use the following methods, in order of importance:

1. **problems tool**: ALWAYS check for code errors regularly using your file problems tool, as this will quickly highlight issues.
2. **dedicated check Tasks**: use these after you have completed a task or set of changes.
3. **unit tests**: run unit tests after an entire, complete change has passed all previous checks.

## contribution guidelines

### commit instructions

- commit messages: use conventional commit style, e.g., feat(frontend): add new chat component
- ensure breaking changes are properly marked with `!`, e.g., feat!: change API response format

### PR instructions

- branch naming: use conventional commit style, e.g., feat/frontend/add-chat-component
- title format: use conventional commit style, e.g., feat(frontend): add new chat component
- body: see /.github/PULL_REQUEST_TEMPLATE.md for details
