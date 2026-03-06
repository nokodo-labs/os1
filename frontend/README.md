# nokodo AI • frontend (SvelteKit)

## Scripts (source of truth)

- `npm run dev` – SvelteKit dev server (port 888 via Vite config)
- `npm run build` – adapter-static build to `build/`
- `npm run preview` – preview built app
- `npm run check` / `check:watch` – Svelte + TS checks
- `npm run lint` – ESLint (Svelte + TS)
- `npm run format` – Prettier with Svelte/Tailwind plugins
- `npm run test` / `test:watch` / `test:ui` / `test:coverage` – Vitest + @testing-library/svelte (happy-dom)
- `npm run generate:api-types` – OpenAPI → `src/lib/api/types.ts`

## Editor/Tasks

VS Code tasks mirror these scripts (see `.vscode/tasks.json`): install, dev, build, check, lint, format, tests, coverage, generate API types.

## Paths

- App shell: `src/routes/+layout.svelte`, `src/routes/+page.svelte`, `src/routes/chats/[id]/+page.svelte`
- Global styles: `src/app.css`
- Components/utilities: `src/lib/**`
- Static assets: `static/`

## Testing

- Unit/component tests: `npm run test`
- Coverage: `npm run test:coverage`
- Type/lint: `npm run check`, `npm run lint`

## Build & Docker

- Static output: `build/`
- Nginx container expects `build/` (see `.docker/Dockerfile.frontend`)

## Runtime config

Runtime config is loaded in two steps:

1. Public config from the frontend origin at `GET /config.json` (generated at container start; see `docker-entrypoint.sh`)
2. Server-provided config from the API at `GET /v1/system/config` (typed client) for values the backend can provide.
