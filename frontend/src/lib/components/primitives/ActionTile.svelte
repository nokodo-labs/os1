<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import type { Component, Snippet } from 'svelte'

	interface Props {
		label: string
		/** every icon in the set takes a class; that is all a tile needs from one. */
		icon?: Component<{ class?: string }>
		/** custom glyph, for icons that need props of their own (mime types) */
		children?: Snippet
		/** renders as a link instead of a button */
		href?: string
		newTab?: boolean
		onclick?: () => void | Promise<void>
		disabled?: boolean
		/** shown shimmering in place of the label while the action runs */
		workingLabel?: string | null
	}

	let {
		label,
		icon: Icon,
		children,
		href,
		newTab = true,
		onclick,
		disabled = false,
		workingLabel = null,
	}: Props = $props()

	const wrapperClass =
		'group flex w-[4.75rem] shrink-0 snap-start cursor-pointer flex-col items-center gap-2 bg-transparent p-0 text-center no-underline outline-none disabled:cursor-not-allowed disabled:opacity-45'
	const tileClass =
		'liquid-glass text-foreground/85 flex h-14 w-14 items-center justify-center rounded-[18px] group-hover:bg-foreground/10 group-active:scale-[0.9] group-focus-visible:ring-2 group-focus-visible:ring-(--accent-primary)/50'
	const labelClass = 'text-foreground/65 w-full text-[11px] leading-tight break-words'
</script>

{#snippet body()}
	<span class="action-tile {tileClass}">
		{#if children}
			{@render children()}
		{:else if Icon}
			<Icon class="h-6 w-6" />
		{/if}
	</span>
	<span class={labelClass}>
		{#if workingLabel}
			<ShimmerText className="inline-block">{workingLabel}</ShimmerText>
		{:else}
			{label}
		{/if}
	</span>
{/snippet}

{#if href}
	<a
		class={wrapperClass}
		{href}
		target={newTab ? '_blank' : undefined}
		rel="external noopener noreferrer"
	>
		{@render body()}
	</a>
{:else}
	<button type="button" class={wrapperClass} {onclick} {disabled}>
		{@render body()}
	</button>
{/if}

<style>
	/* the unlayered .liquid-glass transition shorthand outranks the utilities,
	   so the tile's press and hover response has to be named here. */
	.action-tile {
		transition:
			background var(--lg-transition),
			box-shadow var(--lg-transition),
			scale var(--lg-transition);
	}
</style>
