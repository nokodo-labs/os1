<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Notification from '$lib/components/system/Notification.svelte'
	import { formatToolEventLine, type ToolExecution } from '$lib/tools'
	import BaseToolCard from './BaseToolCard.svelte'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()

	let notificationPreview = $derived(
		(() => {
			const args = execution.toolCall.arguments
			const title = typeof args.title === 'string' ? args.title : null
			const body = typeof args.body === 'string' ? args.body : null
			const iconUrl = typeof args.icon_url === 'string' ? args.icon_url : null
			if (!title && !body) return null
			return { title: title ?? 'sending notification…', body: body ?? '', iconUrl }
		})()
	)
</script>

<BaseToolCard {execution} {compact}>
	{#snippet icon()}
		<AppNotification
			className={`h-4 w-4 text-white/80 ${execution.status === 'running' ? 'animate-pulse' : ''}`}
		/>
	{/snippet}

	{#snippet body()}
		{#if notificationPreview}
			<Notification
				notification={{
					id: execution.toolCall.id,
					user_id: '',
					event_id: '',
					dismissed: false,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString(),
					read_at: null,
				}}
				iconUrl={notificationPreview.iconUrl}
				title={notificationPreview.title}
				body={notificationPreview.body}
				timestamp={new Date()}
				isUnread={true}
			/>
		{:else if execution.status === 'running' || execution.status === 'pending'}
			<div class="animate-pulse space-y-2 rounded-xl bg-white/5 p-3">
				<div class="h-3 w-32 rounded bg-white/10"></div>
				<div class="h-3 w-48 rounded bg-white/10"></div>
			</div>
		{/if}

		{#if execution.events.length > 0}
			<div class="mt-3 space-y-1">
				{#each execution.events as event (event.id)}
					<div class="flex items-start gap-2 text-xs text-white/60">
						<span class="text-white/30">{event.timestamp.toLocaleTimeString()}</span>
						<span>{formatToolEventLine(event)}</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if execution.status === 'error' && execution.error}
			<div class="mt-3 text-sm text-red-300">{execution.error}</div>
		{/if}
	{/snippet}
</BaseToolCard>
