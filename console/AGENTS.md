# nokodo AI console guidelines

## purpose

- dedicated admin-only surface for operators; never exposed publicly
- utilitarian UX focused on clarity and velocity, not polish
- ships as its own Vite app on port 8383 so it can live behind VPN/ACLs or separate auth flows

## tech stack

- Svelte 5 (runes) + TypeScript strict mode
- Vite 7 + PostCSS + TailwindCSS 4 baseline
- SvelteKit + static adapter
- shadcn-svelte components kept stock (no heavy theming) for speed and consistency
- only foundational deps (svelte, tailwind, vite, svelte-check, etc.). do **not** add extra libraries without explicit approval
- prettier with tabs (useTabs=true, tabWidth=4); single quotes, no semicolons; run `pnpm run format`
- pnpm as package manager (not npm)

## ui/ux directives

- prefer default shadcn-svelte/Bits primitives for low-friction dev
- use Tailwind tokens sparingly; readability > aesthetics
- keep layouts responsive but focus on data density and administrative clarity
- lowercase typography is optional here-legibility first
- use rounded corners (rounded-xl or rounded-2xl) for a softer, modern feel

## security & access

- console consumes the same backend API but must authenticate with admin-only scopes/clients
- assume it is deployed behind SSO + MFA; never rely on “secret URL” access
- self-hosted installs should firewall the console separately from the public frontend
- destructive actions require confirmations and should leave audit hooks ready

## dev workflow

- work inside `/console`; keep configs independent from `/frontend`
- share code with the frontend only through an intentional shared package if duplication becomes painful
- run `pnpm install`, then `pnpm run dev -- --port 8383` for local work (don't start servers unless user asks)
- refer to `testing` section to know how to validate formatting and quality of your code

## testing

there are several available layers of checks and tests:

- smoke test with `pnpm run check` (svelte-check)
- formatting with `pnpm run format` (prettier)
- linting with `pnpm run lint` (eslint)
- check for file Problems with the built-in VSCode tool
- api codegen: keep backend running, then use the single task `Console: Generate API (types + client)` (runs `pnpm run generate:api`).
