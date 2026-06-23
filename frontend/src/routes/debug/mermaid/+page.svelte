<script lang="ts">
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import { wheelZoom, type WheelZoomActivation } from '$lib/components/streamdown/Mermaid.svelte'

	const modes: { value: WheelZoomActivation; label: string; hint: string }[] = [
		{ value: 'modifier', label: 'modifier', hint: 'hold ctrl + scroll to zoom' },
		{ value: 'hover', label: 'hover', hint: 'scroll after a brief hover to zoom' },
		{ value: 'both', label: 'both', hint: 'either ctrl + scroll or hover + scroll' },
	]

	const bigFlowchart = `\`\`\`mermaid
flowchart TD
    A[client request] --> B{authenticated?}
    B -->|no| C[return 401]
    B -->|yes| D[load session]
    D --> E{rate limited?}
    E -->|yes| F[return 429]
    E -->|no| G[route handler]
    G --> H[(database)]
    G --> I[[task queue]]
    H --> J[serialize response]
    I --> K[background worker]
    K --> L[send notification]
    J --> M[return 200]
    L --> N[update read model]
    N --> H
\`\`\``

	const sequence = `\`\`\`mermaid
sequenceDiagram
    participant U as user
    participant F as frontend
    participant A as api
    participant W as worker
    U->>F: send message
    F->>A: POST /chat
    A->>W: enqueue task
    A-->>F: stream tokens
    W-->>A: result ready
    A-->>F: final event
    F-->>U: render
\`\`\``
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<h1 class="text-xl font-semibold">mermaid wheel-zoom lab</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		switch how scroll-wheel zoom is gated on mermaid charts and compare the interaction styles.
		the choice persists in localStorage and applies everywhere.
	</p>

	<section class="mt-8">
		<h2 class="text-foreground/70 text-sm font-medium">wheel-zoom activation</h2>
		<div class="mt-3 flex flex-wrap gap-2">
			{#each modes as mode (mode.value)}
				<button
					type="button"
					class="rounded-lg border px-4 py-2 text-sm transition {wheelZoom.mode ===
					mode.value
						? 'border-foreground/30 bg-foreground/10 text-foreground'
						: 'border-foreground/10 bg-foreground/5 text-foreground/70 hover:bg-foreground/10'}"
					onclick={() => (wheelZoom.mode = mode.value)}
				>
					{mode.label}
				</button>
			{/each}
		</div>
		<p class="text-muted-foreground mt-2 text-xs">
			{modes.find((m) => m.value === wheelZoom.mode)?.hint}
		</p>
	</section>

	<!-- remount charts on mode change so each panzoom picks up the new activation -->
	{#key wheelZoom.mode}
		<section class="mt-8 space-y-8">
			<div>
				<h2 class="text-foreground/70 mb-2 text-sm font-medium">flowchart</h2>
				<MarkdownRenderer content={bigFlowchart} />
			</div>
			<div>
				<h2 class="text-foreground/70 mb-2 text-sm font-medium">sequence diagram</h2>
				<MarkdownRenderer content={sequence} />
			</div>
		</section>
	{/key}
</div>
