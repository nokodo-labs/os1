<script lang="ts">
	import type { Snippet } from 'svelte'
	import type { HTMLButtonAttributes } from 'svelte/elements'

	interface MenuItemProps extends Omit<HTMLButtonAttributes, 'class'> {
		icon?: Snippet
		children: Snippet
		destructive?: boolean
		selected?: boolean
		class?: string
	}

	let {
		icon,
		children,
		destructive = false,
		selected = false,
		class: className = '',
		disabled,
		...rest
	}: MenuItemProps = $props()

	const baseClasses =
		'flex w-full cursor-pointer items-center gap-3 rounded-pill border-none bg-transparent px-3 py-2 text-left text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground/40 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-40'

	const textClasses = $derived(
		destructive
			? 'text-red-400 hover:bg-red-500/15 hover:text-red-300'
			: 'text-foreground/85 hover:bg-foreground/10 hover:text-foreground'
	)

	const selectedClasses = $derived(selected ? 'bg-foreground/10 text-foreground' : '')
</script>

<button
	type="button"
	role="menuitem"
	class="{baseClasses} {textClasses} {selectedClasses} {className}"
	{disabled}
	{...rest}
>
	{#if icon}
		<span class="flex h-5 w-5 shrink-0 items-center justify-center *:h-full *:w-full">
			{@render icon()}
		</span>
	{/if}
	<span class="flex-1 truncate">
		{@render children()}
	</span>
</button>

<style>
	button {
		-webkit-tap-highlight-color: transparent;
	}
</style>
