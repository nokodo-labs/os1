<script lang="ts">
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import EllipsisVertical from '$lib/components/icons/EllipsisVertical.svelte'
	import SidebarListItem from '$lib/components/sidebar/SidebarListItem.svelte'
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
				class="rounded-pill flex h-8 w-8 items-center justify-center text-white/80 {rowIconBackground
					? 'bg-white/8'
					: ''}"
			>
				<CheckBox variant="solid" class="h-5 w-5" />
			</span>
		{:else}
			<span
				class="rounded-pill flex h-8 w-8 items-center justify-center text-white"
				style:background-color={leadingInfo.color ?? 'rgba(255,255,255,0.08)'}
			>
				<span class="text-sm">{leadingInfo.emoji}</span>
			</span>
		{/if}
	{/snippet}

	<span class="flex min-w-0 items-center gap-2">
		<span class="min-w-0 truncate text-[0.95rem] font-medium text-white/90">{title}</span>
		{#if count !== null && count > 0}
			<span class="text-xs text-white/55">{count}</span>
		{/if}
	</span>

	{#snippet actions()}
		{#if onMenu}
			<button
				type="button"
				class="rounded-circle inline-flex h-8 w-8 cursor-pointer items-center justify-center border border-transparent bg-transparent text-white/65 transition-all duration-150 hover:border-white/10 hover:bg-white/5 hover:text-white"
				aria-label="list options"
				onclick={(event) => {
					event.stopPropagation()
					onMenu(event)
				}}
			>
				<EllipsisVertical class="h-4 w-4" />
			</button>
		{/if}
	{/snippet}
</SidebarListItem>
