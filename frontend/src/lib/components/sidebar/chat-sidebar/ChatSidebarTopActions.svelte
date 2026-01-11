<script lang="ts">
	import Search from '$lib/components/icons/Search.svelte'
	import * as Tooltip from '$lib/components/ui/tooltip'

	type TriggerProps = Record<string, unknown>

	type SidebarItem = {
		id: string
		icon: typeof Search
		label: string
		action: () => void | Promise<void>
	}

	export let isCompactLayout: boolean
	export let showTopLabels: boolean
	export let items: SidebarItem[]
	export let onSearchClick: () => void
</script>

<!-- Search -->
<Tooltip.Root delayDuration={300} disabled={!isCompactLayout}>
	<Tooltip.Trigger>
		{#snippet child({ props }: { props: TriggerProps })}
			<button
				{...props}
				class="relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
				onclick={onSearchClick}
				aria-label="Search"
			>
				<div class="flex h-12 w-12 shrink-0 items-center justify-center">
					<Search className="h-5 w-5" />
				</div>
				<span
					class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,transform,max-width] duration-200 ease-out {showTopLabels
						? 'max-w-40 translate-x-0 opacity-100'
						: 'max-w-0 -translate-x-1 opacity-0'}"
					aria-hidden={!showTopLabels}
				>
					search
				</span>
			</button>
		{/snippet}
	</Tooltip.Trigger>
	{#if isCompactLayout}
		<Tooltip.Content
			side="right"
			class="rounded-2xl border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
		>
			<p>search</p>
		</Tooltip.Content>
	{/if}
</Tooltip.Root>

<!-- Main Actions -->
{#each items as item (item.id)}
	{@const Icon = item.icon}
	<Tooltip.Root delayDuration={300} disabled={!isCompactLayout}>
		<Tooltip.Trigger>
			{#snippet child({ props }: { props: TriggerProps })}
				<button
					{...props}
					class="relative flex h-12 w-full shrink-0 cursor-pointer items-center rounded-full border border-transparent bg-transparent py-0 text-white transition-all duration-200 hover:border-white/10 hover:bg-white/5"
					onclick={item.action}
					aria-label={item.label}
				>
					<div class="flex h-12 w-12 shrink-0 items-center justify-center">
						<Icon className="h-5 w-5" />
					</div>
					<span
						class="min-w-0 overflow-hidden text-sm font-medium whitespace-nowrap transition-[opacity,transform,max-width] duration-200 ease-out {showTopLabels
							? 'max-w-44 translate-x-0 opacity-100'
							: 'max-w-0 -translate-x-1 opacity-0'}"
						aria-hidden={!showTopLabels}
					>
						{item.label}
					</span>
				</button>
			{/snippet}
		</Tooltip.Trigger>
		{#if isCompactLayout}
			<Tooltip.Content
				side="right"
				class="rounded-2xl border border-white/10 bg-black/90 px-3 py-2 text-sm text-white shadow-[0_4px_12px_rgba(0,0,0,0.3)]"
			>
				<p>{item.label}</p>
			</Tooltip.Content>
		{/if}
	</Tooltip.Root>
{/each}
