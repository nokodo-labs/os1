<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Notification } from '$lib/stores/notifications.svelte'

	interface Props {
		notification: Notification
		iconUrl?: string | null
		imageUrl?: string | null
		title: string
		body: string
		timestamp: Date
		isUnread: boolean
		onMarkRead?: (id: string) => void
		onDismiss?: (id: string) => void
	}

	let {
		notification,
		iconUrl = null,
		imageUrl = null,
		title,
		body,
		timestamp,
		isUnread,
		onMarkRead,
		onDismiss,
	}: Props = $props()

	let expanded = $state(false)

	const truncateLimit = $derived(device.isMobile ? 45 : 70)
	const overflows = $derived(body.length > truncateLimit || !!imageUrl)
	const displayBody = $derived(
		expanded || !overflows ? body : body.slice(0, truncateLimit).trimEnd() + '…'
	)

	// auto-mark-read when visible: only for non-overflowing notifications
	$effect(() => {
		if (isUnread && !overflows && onMarkRead) {
			onMarkRead(notification.id)
		}
	})

	function toggleExpand() {
		expanded = !expanded
		if (expanded && isUnread && onMarkRead) {
			onMarkRead(notification.id)
		}
	}
</script>

<LiquidGlass
	class="relative flex items-start gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-150"
>
	<div
		class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/8 text-white/85"
	>
		{#if iconUrl}
			<img src={iconUrl} alt="" class="h-5 w-5 rounded-full object-cover" />
		{:else}
			<AppNotification class="h-5 w-5" />
		{/if}
	</div>

	<div class="min-w-0 flex-1">
		<div
			class="flex min-w-0 items-center gap-2 text-[0.8125rem] font-semibold {isUnread
				? 'text-white/90'
				: 'text-white/70'}"
		>
			<span class="min-w-0 truncate">{title}</span>
			{#if isUnread}
				<span class="h-1.5 w-1.5 shrink-0 rounded-full bg-blue-400"></span>
			{/if}
		</div>

		<div class="text-[0.8125rem] {isUnread ? 'text-white/60' : 'text-white/55'}">
			{displayBody}
		</div>

		<div
			class="grid transition-[grid-template-rows] duration-300 ease-out {expanded
				? 'grid-rows-[1fr]'
				: 'grid-rows-[0fr]'}"
		>
			<div class="overflow-hidden">
				{#if overflows}
					<div
						class="pt-0.5 text-[0.8125rem] {isUnread
							? 'text-white/60'
							: 'text-white/55'}"
					>
						{body.slice(truncateLimit)}
					</div>
				{/if}
				{#if imageUrl}
					<img
						src={imageUrl}
						alt=""
						class="mt-2 max-h-48 w-full rounded-xl object-cover"
					/>
				{/if}
			</div>
		</div>

		<div class="mt-1 flex items-center gap-2">
			<Timestamp
				{timestamp}
				mode="relative"
				minUnit="minute"
				className="block text-[0.6875rem] text-white/50"
			/>
			{#if overflows}
				<button
					type="button"
					class="flex items-center gap-0.5 text-[0.6875rem] text-white/40 transition-colors hover:text-white/70"
					onclick={toggleExpand}
				>
					<ChevronDown
						class="h-3 w-3 transition-transform duration-300 {expanded
							? 'rotate-180'
							: ''}"
					/>
					<span>{expanded ? 'less' : 'more'}</span>
				</button>
			{/if}
		</div>
	</div>

	{#if onDismiss}
		<XMark
			class="mt-0.5 size-5 shrink-0 cursor-pointer text-white/45 transition-all duration-150 hover:scale-[1.05] hover:text-white/80 active:scale-[0.97]"
			onclick={() => onDismiss?.(notification.id)}
		/>
	{/if}
</LiquidGlass>
