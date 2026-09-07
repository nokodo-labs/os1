<script lang="ts">
	import type { Component, Snippet } from 'svelte'

	// the one popup-menu section label. leading icon optional; a header that is not the
	// first child of the menu gets extra room above it so groups read apart.
	type HeaderIcon = Component<{ class?: string }>

	interface Props {
		icon?: HeaderIcon
		children: Snippet
	}

	let { icon: Icon, children }: Props = $props()
</script>

<div
	class="text-foreground/50 flex items-center gap-2 px-3 pt-3 pb-2 text-xs font-semibold tracking-[0.08em] uppercase first:pt-1"
>
	{#if Icon}
		<Icon class="size-3.5 shrink-0" />
	{/if}
	{@render children()}
</div>
