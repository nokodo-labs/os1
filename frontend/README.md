# nokodo AI • frontend (SvelteKit)

## scripts (source of truth)

- `npm run dev` - SvelteKit dev server (port 888 via Vite config)
- `npm run build` - adapter-static build to `build/`
- `npm run preview` - preview built app
- `npm run check` / `check:watch` - Svelte + TS checks
- `npm run lint` - ESLint (Svelte + TS)
- `npm run format` - Prettier with Svelte/Tailwind plugins
- `npm run test` / `test:watch` / `test:ui` / `test:coverage` - Vitest + @testing-library/svelte (happy-dom)
- `npm run generate:api-types` - OpenAPI → `src/lib/api/types.ts`

## editor/tasks

VS Code tasks mirror these scripts (see `.vscode/tasks.json`): install, dev, build, check, lint, format, tests, coverage, generate API types.

## paths

- app shell: `src/routes/+layout.svelte`, `src/routes/+page.svelte`, `src/routes/chats/[id]/+page.svelte`
- global styles: `src/app.css`
- components/utilities: `src/lib/**`
- static assets: `static/`

## testing

- unit/component tests: `npm run test`
- coverage: `npm run test:coverage`
- type/lint: `npm run check`, `npm run lint`

## build & Docker

- static output: `build/`
- nginx container expects `build/` (see `.docker/Dockerfile.frontend`)

## runtime config

runtime config is loaded in two steps:

1. public config from the frontend origin at `GET /config.json` (generated at container start; see `docker-entrypoint.sh`)
2. server-provided config from the API at `GET /v1/system/config` (typed client) for values the backend can provide.
