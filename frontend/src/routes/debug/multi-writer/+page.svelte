<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { DEBUG_SCENARIOS, type DebugScenario } from '$lib/chat/debugScenarios'
	import { chat as chatStore } from '$lib/stores/chat.svelte'
	import { session } from '$lib/stores/session.svelte'

	let seeded = $state<string | null>(null)

	const viewerId = $derived(session.currentUserId ?? 'user_debugviewer0000000000000')

	/**
	 * seed the thread cache, then open the real thread page.
	 *
	 * the page's loader reads a fresh cache entry instead of calling the API, so
	 * the transcript renders through its ordinary path - no props injected, no
	 * components stubbed. what appears here is what production renders.
	 */
	function open(scenario: DebugScenario): void {
		const { thread, messages } = scenario.build(viewerId)
		chatStore.threadCache.invalidateAll(thread.id)
		chatStore.threadCache.set(thread)
		chatStore.threadCache.setMessages(thread.id, messages, true)
		// no events exist for synthetic messages; an empty set stops the page
		// from asking the API for them
		chatStore.threadCache.setEvents(
			thread.id,
			[],
			messages.map((m) => m.id)
		)
		seeded = scenario.id
		void goto(resolve(`/c/${thread.id}` as unknown as '/'))
	}
</script>

<div class="mx-auto w-full max-w-4xl px-6 pt-10 pb-24">
	<h1 class="text-xl font-semibold">multi-writer transcript</h1>
	<p class="text-muted-foreground mt-2 text-sm">
		seeds a synthetic conversation into the thread cache and opens the real chat page. nothing
		is stubbed - the transcript renders exactly as it would in production.
	</p>
	<p class="text-muted-foreground mt-2 text-sm">
		sending, retrying or otherwise writing will fail: the thread does not exist server-side.
		these are for reading the UI, not driving it.
	</p>

	<div class="mt-6 grid gap-3">
		{#each DEBUG_SCENARIOS as scenario (scenario.id)}
			<button
				type="button"
				class="border-foreground/10 bg-foreground/5 hover:border-foreground/20 hover:bg-foreground/8 cursor-pointer rounded-xl border px-4 py-3 text-left transition"
				onclick={() => open(scenario)}
			>
				<div class="text-foreground/90 text-sm font-semibold">
					{scenario.label}
					{#if seeded === scenario.id}
						<span class="text-foreground/50 font-normal">(seeded)</span>
					{/if}
				</div>
				<div class="text-muted-foreground mt-1 text-sm">{scenario.description}</div>
			</button>
		{/each}
	</div>
</div>
