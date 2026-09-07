<script lang="ts">
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import { device } from '$lib/stores/device.svelte'

	interface Props {
		title: string
		subtitle?: string | null
		count?: number | null
		selected: boolean
		emoji: string
		emojiColor?: string | null
		onSelect: () => void
		onPrefetch?: () => void
		onMenu?: (event: MouseEvent) => void
	}

	let {
		title,
		subtitle = null,
		count = null,
		selected,
		emoji,
		emojiColor = null,
		onSelect,
		onPrefetch,
		onMenu,
	}: Props = $props()
</script>

<SidebarListItem
	{selected}
	{onSelect}
	{onPrefetch}
	actionsVisibility={device.isTouch ? 'always' : 'reserve-hover'}
	showChevron={true}
>
	{#snippet leading()}
		<span
			class="rounded-pill text-foreground flex h-8 w-8 items-center justify-center"
			style:background-color={emojiColor ?? 'rgba(255,255,255,0.08)'}
		>
			<span class="text-sm">{emoji}</span>
		</span>
	{/snippet}

	<span class="flex min-w-0 flex-col">
		<span class="flex min-w-0 items-center gap-2">
			<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium"
				>{title}</span
			>
			{#if count !== null && count > 0}
				<span class="text-foreground/55 shrink-0 text-xs">{count}</span>
			{/if}
		</span>
		{#if subtitle}
			<span class="text-foreground/55 min-w-0 truncate text-xs">{subtitle}</span>
		{/if}
	</span>

	{#snippet actions()}
		{#if onMenu}
			<button
				type="button"
				class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border-none bg-transparent transition-all"
				aria-label="list options"
				onclick={(event) => {
					event.stopPropagation()
					onMenu(event)
				}}
			>
				<EllipsisHorizontal class="h-5 w-5" />
			</button>
		{/if}
	{/snippet}
</SidebarListItem>
