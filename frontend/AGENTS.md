# nokodo AI frontend guidelines

## tech stack

- TypeScript strict mode
- Svelte 5 runes only
- shadcn-svelte components with Bits UI primitives
- TailwindCSS for styling
- Vercel AI SDK for AI interactions
- OpenAPI-generated types for type safety
- tabs, unix line endings
- prettier with tabs (useTabs=true, tabWidth=4); single quotes, no semicolons

## UI/UX philosophy

- source of truth for UX: [docs/ux-spec.md](../docs/ux-spec.md)

- **system chrome**: the UI shell is anchored by two persistent elements:
    - the island (top header): floating, semi-transparent, liquid glass header.
        - activity actions (left): contextual controls for the current activity (if any)
        - activity area (center): contextual system activity (music, uploads, generation, etc) — not page/experience-dependent
        - stable controls (right): mostly fixed buttons like home, show dock, user
    - the dock (right sidebar): notifications + quick controls hub; status + control lives here.
- **home is a home screen**: the front page is not just a chat landing page.
    - unified search bar: one input that supports both chat (send message, start chat) and search/navigation.
    - UX clarity rule: non-chat actions must require explicit selection of a suggestion (no accidental navigation when user just wants to chat).
- **liquid UI**: a next-gen aesthetic with liquid elements, combining Apple-inspired liquid glass with an unique mercury-like liquid metal effect. it includes two distinct styles:
    - liquid glass: utilizing glassmorphism and physical effects like refractions, distortions, and more.
    - liquid mercury: resembling a mix of Sorayama's airbrush metallic paint and fluid metal, utilizes shiny reflections and chrome.
- **motion & transitions**: physics-based motion (Motion One). use view transitions api for page-to-page morphing
- **all lowercase**: following the nokodo branding style, only uppercase for acronyms, emphasis, or proper nouns
- **responsive design**: adapts seamlessly to all screen sizes and devices, in dark and light modes
- **modern & premium**: fluid, reactive real-time updates
- **component library**: shadcn-svelte built on Bits UI primitives
- **UX rules**:
    - never expose internal workings in the UI.
    - never expose model details (don’t surface “gpt/claude/etc” as user-facing concepts).
    - progressive disclosure: simple by default; power features appear only when needed.

## dev environment tips

- always cd into /frontend when working on frontend code.

## frontend codebase map

```
frontend/src/
├── app.html                # SvelteKit template shell
├── app.d.ts                # SvelteKit types
├── routes/                 # SvelteKit routes
│   ├── +layout.svelte      # global layout (backgrounds, sidebar)
│   ├── +layout.ts          # SPA mode (ssr=false)
│   ├── +page.svelte        # landing experience
│   └── chats/[id]/+page.svelte # chat threads
├── lib/
│   ├── api/                # type-safe API client (generated types live here)
│   ├── contexts/           # Svelte contexts
│   ├── styles/             # TailwindCSS styles
│   └── components/         # Svelte components
│       ├── backgrounds/    # background components (webgl, etc.)
│       ├── chat/           # chat UI components
│       ├── common/         # common reusable components
│       ├── debug/          # debugging components
│       ├── icons/          # icon components
│       ├── sidebar/        # sidebar components
│       └── primitives/     # shadcn-svelte / Bits UI primitives
├── static/                 # static assets (served at root)
└── app.css                 # global styles (TailwindCSS)
```

## testing instructions

- unit/component tests: `npm run test` (Vitest + @testing-library/svelte, happy-dom)
- coverage: `npm run test:coverage`
- type/lint: `npm run check`, `npm run lint`
- formatting: `npm run format` (prettier)
- api codegen: ensure backend is running, then use the single task `Frontend: Generate API (types + client)` (runs `npm run generate:api`).
