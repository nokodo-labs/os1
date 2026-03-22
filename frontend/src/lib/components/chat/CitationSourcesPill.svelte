<script lang="ts">
	import type { components } from '$lib/api/types'
	import { getSourceConfig } from '$lib/citations/config'

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
</script>

{#if count > 0}
	<button
		type="button"
		aria-label="{count} {count === 1 ? 'source' : 'sources'}"
		class="liquid-glass liquid-glass--frosted text-foreground/80 hover:text-foreground inline-flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-150 active:scale-[0.97]"
		{onclick}
	>
		<span class="flex items-center -space-x-1.5">
			{#each preview as c, i (c.source_type + ':' + c.source_id)}
				{@const cfg = getSourceConfig(c.source_type)}
				<span
					class="ring-card/80 flex size-5 items-center justify-center rounded-full ring-2 {cfg.iconBg}"
					style="z-index: {3 - i}"
				>
					<cfg.icon variant={cfg.iconVariant} class="size-2.5 {cfg.color}" />
				</span>
			{/each}
		</span>
		<span>{count} {count === 1 ? 'source' : 'sources'}</span>
	</button>
{/if}
