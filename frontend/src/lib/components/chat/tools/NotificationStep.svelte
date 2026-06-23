<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Notification from '$lib/components/system/Notification.svelte'
	import type { Notification as NotificationRecord } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getToolSummary, type ToolExecution } from '$lib/tools'
	import { fade } from 'svelte/transition'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	let isActive = $derived(execution.status === 'pending' || execution.status === 'running')
	let isFailed = $derived(execution.status === 'error')
	let summary = $derived(getToolSummary(execution))
	let notificationPreview = $derived.by((): NotificationRecord | null => {
		const args = execution.toolCall.arguments
		const title = typeof args.title === 'string' ? args.title.trim() : ''
		if (!title) return null
		const body = typeof args.body === 'string' ? args.body : ''
		const event = [...execution.events]
			.reverse()
			.find((item) => item.type === 'tool.notification')
		const timestamp =
			event?.timestamp ?? execution.completedAt ?? execution.startedAt ?? new Date()
		const id = event?.data.notificationId ?? execution.toolCall.id

		return {
			id,
			user_id: session.currentUserId ?? '',
			event_id: event?.id ?? id,
			title,
			body,
			icon_url: null,
			image_url: null,
			badge_url: null,
			action_url: null,
			tag: null,
			data: {},
			actions: [],
			require_interaction: null,
			silent: null,
			renotify: null,
			dismissed: false,
			expires_at: null,
			read_at: null,
			event: null,
			created_at: timestamp.toISOString(),
			updated_at: timestamp.toISOString(),
		}
	})
</script>

<div class="flex items-start gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<div class="relative mt-px flex h-5 w-6 shrink-0 items-center justify-center">
		<AppNotification
			class="h-4.5 w-4.5 {isFailed ? 'text-destructive' : 'text-foreground/80'}"
		/>
	</div>

	<div class="min-w-0 flex-1">
		<div class="flex items-center gap-1.5 text-sm">
			{#if isActive}
				<ShimmerText className="text-foreground/90">{summary.title}</ShimmerText>
			{:else}
				<span class="text-foreground/70">{summary.title}</span>
			{/if}
			{#if summary.subtitle}
				<span class="text-foreground/40 max-w-48 truncate text-xs">{summary.subtitle}</span>
			{/if}
		</div>

		{#if notificationPreview}
			<div class="mt-2 max-w-md">
				<Notification
					notification={notificationPreview}
					title={notificationPreview.title}
					body={notificationPreview.body ?? ''}
					timestamp={new Date(notificationPreview.created_at)}
					isUnread={false}
				/>
			</div>
		{/if}
	</div>
</div>
