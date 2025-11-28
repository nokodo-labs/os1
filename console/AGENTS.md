# nokodo AI console guidelines

## purpose

-   dedicated admin-only surface for operators; never exposed publicly
-   utilitarian UX focused on clarity and velocity, not polish
-   ships as its own Vite app on port 4175 so it can live behind VPN/ACLs or separate auth flows

## tech stack

-   Svelte 5 (runes) + TypeScript strict mode
-   Vite 7 + PostCSS + TailwindCSS 4 baseline
-   shadcn-svelte components kept stock (no heavy theming) for speed and consistency
-   only foundational deps (svelte, tailwind, vite, svelte-check, etc.). do **not** add extra libraries without explicit approval

## ui/ux directives

-   prefer default shadcn-svelte/Bits primitives for low-friction dev
-   use Tailwind tokens sparingly; readability > aesthetics
-   keep layouts responsive but focus on data density and administrative clarity
-   lowercase typography is optional here—legibility first

## security & access

-   console consumes the same backend API but must authenticate with admin-only scopes/clients
-   assume it is deployed behind SSO + MFA; never rely on “secret URL” access
-   self-hosted installs should firewall the console separately from the public frontend
-   destructive actions require confirmations and should leave audit hooks ready

## dev workflow

-   work inside `/console`; keep configs independent from `/frontend`
-   share code only through an intentional shared package if duplication becomes painful
-   run `npm install`, then `npm run dev -- --port 4175` for local work (don’t start servers unless user asks)
-   run `npm run check` before commits; add lint/test scripts later as features appear

## testing

-   smoke test with `npm run check` (svelte-check)
-   future vitest/shadcn stories can live here once we add logic-heavy components
