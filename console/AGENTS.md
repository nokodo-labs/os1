# nokodo AI console guidelines

## code style

- TypeScript strict mode
- Svelte 5 runes only
- TailwindCSS 4 for styling
- OpenAPI-generated types for type safety + OpenAPI-fetch client
- tabs indents, unix line endings
- prettier formatter with tabs; single quotes, no semicolons
- eslint + eslint-plugin-svelte for linting
- pnpm as package manager (not npm)

> **reminder** - CLEAN code means:
>
> 1.  NO `// @ts-ignore` / `// @ts-nocheck` / `<!-- svelte-ignore -->`. if you NEED to use it, you are probably typing something wrong.
> 2.  NO overuse of comments everywhere. comments are good, but only to explain complex or crucial blocks.
> 3.  NO `.skip()` / `.todo()` in tests. update the test to cover the case, or remove unreachable code.
> 4.  NO dynamic property access (obj[key]) unless it's the only way. it defeats type checkers and is ugly.
> 5.  AVOID `as Type` assertions. use only when it's the only way.
> 6.  AVOID `any` type. only use when absolutely necessary.
> 7.  AVOID `!` non-null assertions. narrow the type properly instead.
> 8.  NO `!important` in CSS. if you need it, your specificity is wrong.
> 9.  NO `// eslint-disable` / `// prettier-ignore`. fix the actual issue.
> 10. patterns 1, 4, 5, 6, 7 and 9 can be used to **bypass typing issues**, which is **strictly forbidden**.

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
- lowercase typography is optional here - legibility first
- use rounded corners (rounded-xl or rounded-2xl) for a softer, modern feel

## security & access

- console consumes the same backend API but must authenticate with admin-only scopes/clients
- assume it is deployed behind SSO + MFA; never rely on “secret URL” access
- self-hosted installs should firewall the console separately from the public frontend
- destructive actions require confirmations and should leave audit hooks ready

## dev environment tips

- work inside `/console`; keep configs independent from `/frontend`
- share code with the frontend only through an intentional shared package if duplication becomes painful
- ALWAYS code as if autogen API types were up to date with the backend, even if they might not yet be.

## console codebase map

```
console/
└── src/
    ├── app.html
    ├── app.css
    ├── routes/
    │   ├── +layout.svelte          # root layout (auth guard, shell)
    │   ├── +page.svelte            # redirect to /dashboard
    │   ├── login/
    │   ├── welcome/                # first-run / onboarding
    │   └── (app)/                  # authenticated app shell
    │       ├── +layout.svelte      # sidebar nav + top bar
    │       ├── agents/
    │       ├── dashboard/
    │       ├── files/
    │       ├── groups/
    │       ├── memories/
    │       ├── models/
    │       ├── notes/
    │       ├── playground/
    │       ├── plugins/
    │       ├── prompts/
    │       ├── providers/
    │       ├── reminders/
    │       ├── roles/
    │       ├── settings/           # global platform settings (+page.svelte)
    │       ├── threads/
    │       ├── users/
    │       └── vectors/
    └── lib/
        ├── api/                    # OpenAPI-generated types + client
        ├── auth.svelte.ts          # auth state (runes)
        ├── stores/
        ├── utils/
        ├── utils.ts
        ├── index.ts
        └── components/
            ├── settings/           # per-section settings components
            │   ├── SettingsAI.svelte
            │   ├── SettingsAssets.svelte
            │   ├── SettingsBranding.svelte
            │   ├── SettingsDefaultPermissions.svelte
            │   ├── SettingsLimits.svelte
            │   ├── SettingsMedia.svelte
            │   ├── SettingsSecurity.svelte
            │   ├── SettingsSoftDelete.svelte
            │   └── SettingsUI.svelte
            ├── ui/                 # shadcn-svelte primitives (auto-generated)
            ├── AclModal.svelte
            ├── CreateRoleModal.svelte
            ├── CreateUserModal.svelte
            ├── DefaultPermissionsEditor.svelte
            ├── EmptyState.svelte
            ├── FileDetailsModal.svelte
            ├── GroupDetailsModal.svelte
            ├── MemoryDetailsModal.svelte
            ├── NokodoLoader.svelte
            ├── NoteDetailsModal.svelte
            ├── PaginatedList.svelte
            ├── PendingApproval.svelte
            ├── PrincipalPicker.svelte
            ├── PromptVariablesLegend.svelte
            ├── ReminderListDetailsModal.svelte
            ├── RoleDetailsModal.svelte
            ├── RolePicker.svelte
            ├── SplashLoader.svelte
            ├── ThreadDetailsModal.svelte
            └── UserDetailsModal.svelte
```

## testing

there are several available layers of checks and tests:

- smoke test with `pnpm run check` (svelte-check)
- formatting with `pnpm run format` (prettier)
- linting with `pnpm run lint` (eslint)
- check for file Problems with the built-in VSCode tool
- api codegen: keep backend running, then use the single task `Console: Generate API (types + client)` (runs `pnpm run generate:api`).
