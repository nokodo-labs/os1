<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { Notification } from '$lib/stores/notifications.svelte'

	interface Props {
		notification: Notification
		iconUrl?: string | null
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
		title,
		body,
		timestamp,
		isUnread,
		onMarkRead,
		onDismiss,
	}: Props = $props()
</script>

<div
	class="group relative flex items-start gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-150 {isUnread
		? 'bg-white/8'
		: 'bg-white/3'} hover:bg-white/10"
>
	<div
		class="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/8 text-white/85"
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
				<span class="h-1.5 w-1.5 rounded-full bg-blue-400"></span>
			{/if}
		</div>
		<div class="truncate text-[0.8125rem] {isUnread ? 'text-white/60' : 'text-white/45'}">
			{body}
		</div>
		<Timestamp
			{timestamp}
			mode="relative"
			minUnit="minute"
			className="mt-1 block text-[0.6875rem] text-white/40"
		/>
	</div>
	<div
		class="absolute top-2 right-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100"
	>
		{#if isUnread && onMarkRead}
			<button
				type="button"
				class="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white/60 transition-colors hover:bg-white/20 hover:text-white/90"
				title="mark as read"
				onclick={() => onMarkRead?.(notification.id)}
			>
				<Check class="h-3 w-3" />
			</button>
		{/if}
		{#if onDismiss}
			<button
				type="button"
				class="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white/60 transition-colors hover:bg-white/20 hover:text-white/90"
				title="dismiss"
				onclick={() => onDismiss?.(notification.id)}
			>
				<XMark class="h-3 w-3" />
			</button>
		{/if}
	</div>
</div>
