# nokodo AI frontend guidelines

## code style

- TypeScript strict mode
- Svelte 5 runes only
- TailwindCSS 4 for styling
- OpenAPI-generated types for type safety + OpenAPI-fetch client
- tabs indents, unix line endings
- prettier formatter with tabs; single quotes, no semicolons
- eslint + eslint-plugin-svelte for linting
- vitest + @testing-library/svelte for testing with coverage
- adhere to `nokodo` brand rule of **no auto-capitalization** in comments, docstrings, logging, or any user-facing text. only proper nouns, acronyms and other intentional capitalizations are allowed.
- pnpm as package manager (not npm)

> **reminder** - CLEAN code means:
>
> 1.  NO `// @ts-ignore` / `// @ts-nocheck` / `<!-- svelte-ignore -->`. if you NEED to use it, you are probably typing something wrong.
> 2.  NO overuse of comments everywhere. comments are good, but only to explain complex or crucial blocks.
> 3.  NO `.skip()` / `.todo()` in tests. if you need to skip a test, update the test to cover the case, or remove unreachable code instead.
> 4.  NO dynamic property access (obj[key]) unless it's the only way. it defeats type checkers and is ugly.
> 5.  AVOID `as Type` assertions. use only when it's the only way.
> 6.  AVOID `any` type. only use when absolutely necessary.
> 7.  AVOID `!` non-null assertions. narrow the type properly instead.
> 8.  NO `!important` in CSS. if you need it, your specificity is wrong.
> 9.  NO `// eslint-disable` / `// prettier-ignore`. fix the actual issue.
> 10. patterns 1, 4, 5, 6, 7 and 9 can be used to **bypass typing issues**, which is **strictly forbidden**.

## UI/UX philosophy

- source of truth for UX: [docs/ux-spec.md](../docs/ux-spec.md)

- **system chrome**: the UI shell is anchored by two persistent elements:
    - the island (top header): floating, semi-transparent, liquid glass header.
        - activity actions (left): contextual controls for the current activity (if any)
        - activity area (center): contextual system activity (music, uploads, generation, etc) - not page/experience-dependent
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

## dev environment rules

- always cd into /frontend when working on frontend code.
- ALWAYS code as if autogen API types were up to date with the backend, even if they might not yet be.

## frontend codebase map

```
frontend/
├── src/
│   ├── app.html
│   ├── app.d.ts
│   ├── app.css
│   ├── service-worker.ts
│   ├── routes/
│   │   ├── +error.svelte
│   │   ├── +layout.svelte
│   │   ├── +layout.ts
│   │   ├── +page.svelte
│   │   ├── c/[id]/
│   │   ├── debug/
│   │   │   ├── +page.svelte
│   │   │   ├── backgrounds/
│   │   │   ├── liquid-glass/
│   │   │   ├── liquid-metal/
│   │   │   ├── pwa/
│   │   │   ├── runs/
│   │   │   └── shimmer/
│   │   ├── library/
│   │   ├── login/
│   │   ├── notes/
│   │   │   └── [id]/
│   │   ├── projects/
│   │   │   └── [id]/
│   │   ├── reminders/
│   │   │   └── lists/[listId]/
│   │   ├── settings/
│   │   │   ├── about/
│   │   │   ├── accessibility/
│   │   │   ├── advanced/
│   │   │   ├── ai/
│   │   │   ├── appearance/
│   │   │   ├── debug/
│   │   │   ├── notifications/
│   │   │   ├── privacy/
│   │   │   └── security/
│   │   ├── signup/
│   │   └── social/
│   │       ├── (tabs)/
│   │       │   ├── friends/
│   │       │   └── groups/
│   │       ├── groups/[id]/
│   │       └── users/[id]/
│   ├── lib/
│   │   ├── actions/
│   │   ├── api/
│   │   │   └── streaming/
│   │   ├── auth/
│   │   ├── chat/
│   │   ├── citations/        # centralized citation source config (icon, color, href, widget per source type)
│   │   ├── collaboration/
│   │   ├── components/
│   │   │   ├── backgrounds/ (webgl/)
│   │   │   ├── chat/ (sidebar/, tools/, webgl/)
│   │   │   ├── common/
│   │   │   ├── editor/
│   │   │   ├── effects/
│   │   │   ├── home/
│   │   │   ├── icons/
│   │   │   ├── layouts/
│   │   │   ├── markdown/
│   │   │   ├── modals/
│   │   │   ├── notes/
│   │   │   ├── primitives/ (liquid-glass/)
│   │   │   ├── reminders/
│   │   │   ├── settings/
│   │   │   ├── streamdown/ (utils/)
│   │   │   ├── system/
│   │   │   └── widgets/
│   │   ├── config/
│   │   ├── contexts/
│   │   ├── liquid-glass/ (a/, b/)
│   │   ├── liquid-mercury/ (b/)
│   │   ├── liquid-metal/ (svg/)
│   │   ├── stores/           # see stores/README.md for architecture + lifecycle contract
│   │   ├── styles/
│   │   ├── tools/
│   │   ├── utils/
│   │   ├── init.ts
│   │   ├── index.ts
│   │   └── utils.ts
│   └── test/
│       ├── README.md
│       ├── setup.ts
│       └── api/v1/
└── static/
    ├── backgrounds/
    ├── config.json
    ├── offline.html
    ├── robots.txt
    ├── shimmer.css
    ├── splash-preview.html
    └── splash.css
```

## core, frequently used components (/src/lib/components)

- shell and system chrome
    - `system/Island.svelte`
    - `system/Dock.svelte`
- page scaffolds
    - `layouts/MasterDetailScaffold.svelte`
    - `layouts/TabIslandScaffold.svelte`
- common
    - `/Timestamp.svelte`
    - `/NokodoLoader.svelte`
    - `/PageTitle.svelte`
    - `/DeleteButton.svelte`
    - `/SidebarListItem.svelte`
    - `/Tooltip.svelte`
- effects at `/effects/`
    - `ShimmerText.svelte` - **required** for any label representing an in-progress/ongoing state (loading, deleting, enhancing, processing, saving, etc.). never use plain text like `"loading..."` for ongoing operations.
- primitives at `/primitives/`

## testing instructions

- unit/component tests: `Frontend: Test Coverage`
- type/lint: `Frontend: Check`, `Frontend: Lint`
- formatting: `Frontend: Format`
- api codegen: `Frontend: Generate API`.
