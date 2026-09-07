<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import type { Component, Snippet } from 'svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	// the one popup-menu row. every menu row renders through here, so label weight,
	// icon size, row height, hover fill and destructive colour live here alone -
	// there is deliberately no `class` escape hatch.
	// menu icons are outline (F26 rule 2), except the selected row of a filter / sort /
	// group-by list, which renders its icon solid (F115); pass a plain icon component here
	// and MenuItem renders it at the menu weight/size. no list of exceptions is kept: an
	// icon with nothing to fill (SortIcon, Clip) simply declares no `variant` prop, so the
	// ask lands in its attribute rest and its single drawing is what renders.
	// `iconSnippet` stays for composite glyphs - those carry the same variant themselves.
	type MenuIcon = Component<{ class?: string; variant?: 'outline' | 'solid' }>

	interface MenuItemProps extends Omit<HTMLButtonAttributes, 'class'> {
		icon?: MenuIcon
		iconSnippet?: Snippet
		trailing?: Snippet
		/** secondary line under the label, for rows that carry more than a name. */
		detail?: Snippet
		children: Snippet
		destructive?: boolean
		selected?: boolean
		/** set on a row that opens a submenu: adds the chevron and the open highlight. */
		submenuOpen?: boolean
	}

	let {
		icon: Icon,
		iconSnippet,
		trailing,
		detail,
		children,
		destructive = false,
		selected = false,
		submenuOpen,
		disabled,
		...rest
	}: MenuItemProps = $props()

	const isSubmenu = $derived(submenuOpen !== undefined)
	const highlighted = $derived(selected || submenuOpen === true)

	const baseClasses =
		'flex min-h-11 w-full min-w-0 cursor-pointer items-center gap-3 rounded-pill border-none bg-transparent px-3 py-2.5 text-left text-sm font-normal transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40'

	const toneClasses = $derived(
		destructive
			? 'text-red-400 hover:bg-red-500/15 hover:text-red-300'
			: 'text-foreground/85 hover:bg-foreground/10 hover:text-foreground'
	)

	const highlightClasses = $derived(
		highlighted
			? 'bg-foreground/10 text-foreground shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]'
			: ''
	)
</script>

<button
	type="button"
	role="menuitem"
	aria-haspopup={isSubmenu ? 'menu' : undefined}
	aria-expanded={isSubmenu ? submenuOpen : undefined}
	class="{baseClasses} {toneClasses} {highlightClasses}"
	{disabled}
	{...rest}
>
	{#if Icon || iconSnippet}
		<span
			class="flex size-6 shrink-0 items-center justify-center *:h-full *:w-full {destructive
				? ''
				: 'text-foreground/72'}"
		>
			{#if Icon}
				<Icon class="size-full" variant={selected ? 'solid' : undefined} />
			{:else if iconSnippet}
				{@render iconSnippet()}
			{/if}
		</span>
	{/if}
	<span class="flex min-w-0 flex-1 flex-col gap-0.5">
		<span class="truncate">
			{@render children()}
		</span>
		{#if detail}
			{@render detail()}
		{/if}
	</span>
	{#if trailing}
		<span class="text-foreground/60 flex shrink-0 items-center justify-center">
			{@render trailing()}
		</span>
	{/if}
	{#if isSubmenu}
		<ChevronRight class="text-foreground/45 size-4 shrink-0" />
	{:else if selected}
		<Check class="text-foreground size-4 shrink-0" strokeWidth="2" />
	{/if}
</button>

<style>
	button {
		-webkit-tap-highlight-color: transparent;
	}
</style>
