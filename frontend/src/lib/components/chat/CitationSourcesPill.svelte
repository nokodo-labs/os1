<script lang="ts">
	import type { components } from '$lib/api/types'
	import Brain from '$lib/components/icons/Brain.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'

	type Citation = components['schemas']['Citation']

	interface Props {
		citations: Citation[]
		onclick: () => void
	}

	let { citations, onclick }: Props = $props()

	/** deduplicate by source_type + source_id, keep original order */
	const unique = $derived.by(() => {
		const result: Citation[] = []
		const keys: string[] = []
		for (const c of citations) {
			const key = `${c.source_type}:${c.source_id}`
			if (!keys.includes(key)) {
				keys.push(key)
				result.push(c)
			}
		}
		return result
	})

	const preview = $derived(unique.slice(0, 3))
	const count = $derived(unique.length)
	function iconBg(sourceType: string): string {
		switch (sourceType) {
			case 'note':
				return 'bg-amber-500/20 text-amber-400'
			case 'thread':
				return 'bg-emerald-500/20 text-emerald-400'
			case 'file':
				return 'bg-rose-500/20 text-rose-400'
			case 'url':
				return 'bg-sky-500/20 text-sky-400'
			case 'memory':
				return 'bg-purple-500/20 text-purple-400'
			default:
				return 'bg-orange-500/20 text-orange-400'
		}
	}
</script>

{#if count > 0}
	<button
		type="button"
		class="border-border/40 bg-card/50 text-foreground/70 hover:bg-card/80 hover:text-foreground/90 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium backdrop-blur-sm transition-all duration-150 active:scale-[0.97]"
		{onclick}
	>
		<span class="flex items-center -space-x-1.5">
			{#each preview as c, i (c.source_type + ':' + c.source_id)}
				<span
					class="ring-card/80 flex size-5 items-center justify-center rounded-full ring-2 {iconBg(
						c.source_type
					)}"
					style="z-index: {3 - i}"
				>
					{#if c.source_type === 'note'}
						<Document variant="solid" class="size-2.5" />
					{:else if c.source_type === 'thread'}
						<ChatBubbles variant="solid" class="size-2.5" />
					{:else if c.source_type === 'file'}
						<Document variant="solid" class="size-2.5" />
					{:else if c.source_type === 'url'}
						<GlobeAlt variant="solid" class="size-2.5" />
					{:else if c.source_type === 'memory'}
						<Brain class="size-2.5" />
					{:else}
						<CommandLine class="size-2.5" />
					{/if}
				</span>
			{/each}
		</span>
		<span>{count} {count === 1 ? 'source' : 'sources'}</span>
	</button>
{/if}
