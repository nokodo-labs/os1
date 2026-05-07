<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import type { Snippet } from 'svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	interface MenuItemProps extends Omit<HTMLButtonAttributes, 'class'> {
		icon?: Snippet
		trailing?: Snippet
		children: Snippet
		description?: string
		destructive?: boolean
		selected?: boolean
		class?: string
	}

	let {
		icon,
		trailing,
		children,
		description,
		destructive = false,
		selected = false,
		class: className = '',
		disabled,
		...rest
	}: MenuItemProps = $props()

	const baseClasses =
		'flex w-full min-w-0 cursor-pointer items-center gap-3 rounded-pill border-none bg-transparent px-3 py-2 text-left text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40'

	const textClasses = $derived(
		destructive
			? 'text-red-400 hover:bg-red-500/15 hover:text-red-300'
			: 'text-foreground/85 hover:bg-foreground/10 hover:text-foreground'
	)

	const selectedClasses = $derived(
		selected
			? 'bg-foreground/10 text-foreground shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]'
			: ''
	)
</script>

<button
	type="button"
	role="menuitem"
	class="{baseClasses} {textClasses} {selectedClasses} {className}"
	{disabled}
	{...rest}
>
	{#if icon}
		<span
			class="text-foreground/65 flex h-5 w-5 shrink-0 items-center justify-center *:h-full *:w-full"
		>
			{@render icon()}
		</span>
	{/if}
	<span class="flex min-w-0 flex-1 flex-col">
		<span class="truncate">
			{@render children()}
		</span>
		{#if description}
			<span class="text-foreground/50 mt-0.5 truncate text-xs leading-4">
				{description}
			</span>
		{/if}
	</span>
	{#if trailing}
		<span
			class="text-foreground/60 flex h-5 w-5 shrink-0 items-center justify-center *:h-full *:w-full"
		>
			{@render trailing()}
		</span>
	{:else if selected}
		<Check class="text-foreground h-4 w-4 shrink-0" strokeWidth="2" />
	{/if}
</button>

<style>
	button {
		-webkit-tap-highlight-color: transparent;
	}
</style>
