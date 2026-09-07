<script lang="ts">
	/**
	 * one card of the messages inbox, in the ios inset-grouped-table shape: the
	 * card is the only background, its header sits above it, and whatever it
	 * holds - rows, a skeleton, an empty state - is clipped to its corners.
	 */

	import type { Snippet } from 'svelte'

	interface Props {
		/** lowercase section header, drawn above the card. omitted for a single unnamed card. */
		label?: string
		children: Snippet
	}

	let { label, children }: Props = $props()
</script>

<section class="flex min-w-0 flex-col gap-1.5">
	{#if label}
		<h2 class="text-foreground/45 px-4 text-xs font-medium" data-card-label>{label}</h2>
	{/if}
	<div
		class="liquid-glass liquid-glass--frosted liquid-glass--clip rounded-3xl"
		data-conversation-card
	>
		{@render children()}
	</div>
</section>
