<script lang="ts">
	import { onMount } from 'svelte'

	import Notification from '$lib/components/system/Notification.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import {
		notifications,
		type Notification as NotificationType,
	} from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'

	const chrome = useSystemChrome()

	let controlCenterEl: HTMLElement | null = $state(null)
	let controlCenterHeightPx = $state(0)

	function syncControlCenterHeight(): void {
		controlCenterHeightPx = controlCenterEl?.offsetHeight ?? 0
	}

	onMount(() => {
		syncControlCenterHeight()
		const ro = new ResizeObserver(() => syncControlCenterHeight())
		if (controlCenterEl) ro.observe(controlCenterEl)

		return () => ro.disconnect()
	})

	$effect(() => {
		if (session.isLoggedIn) notifications.init()
		else notifications.cleanup()
	})

	$effect(() => {
		const agentIds: string[] = []
		for (const notif of notifications.list) {
			const data = notif.event?.data as Record<string, unknown> | undefined
			const agentId = data && typeof data.agent_id === 'string' ? data.agent_id : null
			if (agentId) agentIds.push(agentId)
		}
		if (agentIds.length > 0) void agents.ensureMany(agentIds)
	})

	function getNotificationTitle(notif: NotificationType): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (data?.title as string) || notif.event?.type || 'notification'
	}

	function getNotificationBody(notif: NotificationType): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (data?.body as string) || ''
	}

	function getNotificationIcon(notif: NotificationType): string | null {
		const data = notif.event?.data as Record<string, unknown> | undefined
		const explicit = data && typeof data.icon_url === 'string' ? data.icon_url : null
		if (explicit) return explicit

		const agentId = data && typeof data.agent_id === 'string' ? data.agent_id : null
		if (!agentId) return null
		return agents.get(agentId)?.profile_image_url ?? null
	}

	function handleMarkRead(notifId: string): void {
		void notifications.markRead(notifId)
	}

	function handleDismiss(notifId: string): void {
		void notifications.delete(notifId)
	}

	function handleMarkAllRead(): void {
		void notifications.markAllRead()
	}
</script>

<aside class="relative h-full w-full" aria-hidden={!chrome.isDockOpen}>
	<div class="flex h-full flex-col gap-4">
		<section
			data-dock-panel
			class="relative flex min-h-0 flex-col overflow-hidden rounded-2xl bg-white/5 px-5 py-4"
			style={controlCenterHeightPx > 0
				? `max-height: calc(100% - ${controlCenterHeightPx}px - 1rem);`
				: undefined}
			aria-label="notifications"
		>
			<div class="flex min-h-0 flex-col">
				<div class="mb-2 flex items-center justify-between">
					<div class="text-xs font-semibold tracking-wide text-white/60">
						notifications
						{#if notifications.unreadCount > 0}
							<span
								class="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/15 px-1.5 text-[0.6875rem] font-bold text-white/80"
							>
								{notifications.unreadCount}
							</span>
						{/if}
					</div>
					{#if notifications.unreadCount > 0}
						<button
							type="button"
							class="text-xs text-white/50 transition-colors hover:text-white/80"
							onclick={handleMarkAllRead}
						>
							mark all read
						</button>
					{/if}
				</div>
				<div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
					{#if !session.isLoggedIn}
						<div
							class="rounded-pill bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							log in to see notifications
						</div>
					{:else if notifications.list.length === 0}
						<div
							class="rounded-pill bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							no notifications
						</div>
					{:else}
						{#each notifications.list as notif (notif.id)}
							<Notification
								notification={notif}
								iconUrl={getNotificationIcon(notif)}
								title={getNotificationTitle(notif)}
								body={getNotificationBody(notif)}
								timestamp={new Date(notif.created_at)}
								isUnread={!notif.read_at}
								onMarkRead={handleMarkRead}
								onDismiss={handleDismiss}
							/>
						{/each}
					{/if}
				</div>
			</div>
		</section>

		<div class="min-h-0 flex-1" aria-hidden="true"></div>

		<section
			data-dock-panel
			class="relative shrink-0 overflow-hidden rounded-2xl bg-white/5 px-5 py-4"
			aria-label="control center"
			bind:this={controlCenterEl}
		>
			<div class="mb-3 text-xs font-semibold tracking-wide text-white/60">control center</div>

			<div class="grid grid-cols-2 gap-2">
				<button
					class="rounded-pill border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					wifi
				</button>
				<button
					class="rounded-pill border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					bluetooth
				</button>
				<button
					class="rounded-pill border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					focus
				</button>
				<button
					class="rounded-pill border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					dark mode
				</button>
			</div>
		</section>
	</div>
</aside>
