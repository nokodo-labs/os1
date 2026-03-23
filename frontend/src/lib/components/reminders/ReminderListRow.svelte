<script lang="ts">
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import SidebarListItem from '$lib/components/SidebarListItem.svelte'
	import { device } from '$lib/stores/device.svelte'

	type Leading =
		| {
				type: 'checkbox'
		  }
		| {
				type: 'emoji'
				emoji: string
				color?: string | null
		  }

	interface Props {
		title: string
		count?: number | null
		selected: boolean
		leading: Leading
		onSelect: () => void
		onPrefetch?: () => void
		onMenu?: (event: MouseEvent) => void
		rowIconBackground?: boolean
	}

	let {
		title,
		count = null,
		selected,
		leading: leadingInfo,
		onSelect,
		onPrefetch,
		onMenu,
		rowIconBackground = false,
	}: Props = $props()
</script>

<SidebarListItem
	{selected}
	{onSelect}
	{onPrefetch}
	actionsVisibility={device.isTouch ? 'always' : 'hover'}
	showChevron={true}
>
	{#snippet leading()}
		{#if leadingInfo.type === 'checkbox'}
			<span
				class="rounded-pill text-foreground/80 flex h-8 w-8 items-center justify-center {rowIconBackground
					? 'bg-foreground/8'
					: ''}"
			>
				<CheckBox variant="solid" class="h-5 w-5" />
			</span>
		{:else}
			<span
				class="rounded-pill text-foreground flex h-8 w-8 items-center justify-center"
				style:background-color={leadingInfo.color ?? 'rgba(255,255,255,0.08)'}
			>
				<span class="text-sm">{leadingInfo.emoji}</span>
			</span>
		{/if}
	{/snippet}

	<span class="flex min-w-0 items-center gap-2">
		<span class="text-foreground/90 min-w-0 truncate text-[0.95rem] font-medium">{title}</span>
		{#if count !== null && count > 0}
			<span class="text-foreground/55 text-xs">{count}</span>
		{/if}
	</span>

	{#snippet actions()}
		{#if onMenu}
			<button
				type="button"
				class="rounded-circle text-foreground/70 hover:border-foreground/10 hover:bg-foreground/8 hover:text-foreground inline-flex h-9 w-9 cursor-pointer items-center justify-center border border-transparent bg-transparent transition-all duration-150"
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
