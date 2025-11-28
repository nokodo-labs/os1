# nokodo AI

AI platform with agentic coding support, beautiful UI, and comprehensive tooling.

## Stack

-   **Backend**: FastAPI (Python 3.13+), Pydantic AI, SQLAlchemy 2.0+, PostgreSQL 17
-   **Frontend**: Svelte 5, TypeScript, Vite, Vercel AI SDK, shadcn-svelte, TailwindCSS
-   **Admin Console**: TBD
-   **Infra**: Docker Compose, Nginx + static builds, GitHub Actions CI/CD, Release Please

## AI Agent Behavior

### General Guidelines

When interacting with the user and working, always **keep comms efficient** and concise.

As an AI, your context is limited, thus overly verbose responses will directly affect how your performance degrades over time.
**Less is more** - focus on addressing the user's needs never create extra files or documentation to report changes unless explicitly asked.

### Component-Specific Guidelines

You can find additional AGENTS.md files in each of the 3 main components. Refer to those for component-specific instructions, information, and guidelines:

-   backend/AGENTS.md - Backend
-   frontend/AGENTS.md - Frontend
-   admin-console/AGENTS.md - Admin Console

### Plan and Reflect

Before executing any tasks, follow this process:

1. **Read** the user's request carefully.
2. **Fetch and read** any relevant files, documentation, or context.
3. **Think and plan** your approach step-by-step. Use the TODOs tool to stay grounded as you iterate.

Skipping any of these steps will lead to increased costs and suboptimal results.

## Contribution Guidelines

### Commit instructions

-   commit messages: use conventional commit style, e.g., feat(frontend): add new chat component
-   ensure breaking changes are properly marked with `!`, e.g., feat!: change API response format

### PR instructions

-   branch naming: use conventional commit style, e.g., feat/frontend/add-chat-component
-   title format: use conventional commit style, e.g., feat(frontend): add new chat component
-   body: see /.github/PULL_REQUEST_TEMPLATE.md for details
