# nokodo AI frontend guidelines

## tech stack

- TypeScript strict mode
- Svelte 5 runes only
- shadcn-svelte components with Bits UI primitives
- TailwindCSS for styling
- Vercel AI SDK for AI interactions
- OpenAPI-generated types for type safety
- tabs, unix line endings

## UI/UX philosophy

- **liquid UI**: a next-gen aesthetic with liquid elements, unifying Apple-inspired liquid glass with an unique mercury-like liquid metal effect. it includes two distinct styles:
    - liquid glass: utilizing glassmorphism and physical effects like refractions, distortions, and more.
    - liquid mercury: resembling a mix of Sorayama's airbrush metallic paint and fluid metal, utilizes shiny reflections and chrome.
- **physics-based animations**: Motion One for smooth, realistic interactions
- **all lowercase**: following the nokodo branding style, only uppercase for acronyms, emphasis, or proper nouns
- **responsive design**: adapts seamlessly to all screen sizes and devices, in dark and light modes
- **modern & premium**: fluid, reactive real-time updates
- **component library**: shadcn-svelte built on Bits UI primitives

## dev environment tips

- always cd into /frontend when working on frontend code.

## frontend codebase map

```
frontend/src/
├── lib/
│   ├── api/                # type-safe API client
│   ├── contexts/           # Svelte contexts
│   ├── styles/             # TailwindCSS styles
│   └── components/         # Svelte components
│       ├── backgrounds/	# background components
│       │   └── webgl/      # WebGL background components
│       ├── chats/          # chat UI components
│       ├── common/         # common reusable components
│       ├── debug/          # debugging components
│       ├── icons/          # icon components
│       ├── sidebar/        # sidebar components
│       └── primitives/     # shadcn-svelte / Bits UI primitives
├── tests/                  # frontend vitest tests
├── main.ts                 # entrypoint
├── App.svelte              # main Svelte app
└── app.css                 # global styles (TailwindCSS)
```

## testing instructions

- to run frontend tests, cd into `frontend/` and run `npm run test`.
