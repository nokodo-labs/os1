<script lang="ts">
	import Search from '$lib/components/icons/Search.svelte'

	type SidebarItem = {
		id: string
		icon: typeof Search
		label: string
		action: () => void | Promise<void>
	}

	export let showTopLabels: boolean
	export let items: SidebarItem[]
	export let onSearchClick: () => void

	const iconClass = 'h-5 w-5 -translate-x-[0.5px]'

	function stop(event: MouseEvent): void {
		event.stopPropagation()
	}
</script>

<!-- Search -->
<button
	class="text-foreground hover:border-foreground/10 hover:bg-foreground/5 relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 transition-all duration-200"
	onclick={(e) => {
		stop(e)
		onSearchClick()
	}}
	aria-label="Search"
>
	<div class="flex h-12 w-12 shrink-0 items-center justify-center">
		<Search class={iconClass} />
	</div>
	<span
		class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,max-width] duration-200 ease-out {showTopLabels
			? 'max-w-40 opacity-100'
			: 'max-w-0 opacity-0'}"
		aria-hidden={!showTopLabels}
	>
		search
	</span>
</button>

<!-- Main Actions -->
{#each items as item (item.id)}
	{@const Icon = item.icon}
	<button
		class="text-foreground hover:border-foreground/10 hover:bg-foreground/5 relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 transition-all duration-200"
		onclick={(e) => {
			stop(e)
			void item.action()
		}}
		aria-label={item.label}
	>
		<div class="flex h-12 w-12 shrink-0 items-center justify-center">
			<Icon class={iconClass} />
		</div>
		<span
			class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,max-width] duration-200 ease-out {showTopLabels
				? 'max-w-44 opacity-100'
				: 'max-w-0 opacity-0'}"
			aria-hidden={!showTopLabels}
		>
			{item.label}
		</span>
	</button>
{/each}
