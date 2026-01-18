<script lang="ts">
	import { onMount } from 'svelte'

	import Notification from '$lib/components/system/Notification.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { agentsById, ensureAgents } from '$lib/stores/agents.svelte'
	import {
		deleteNotification,
		initNotifications,
		markAllNotificationsRead,
		markNotificationRead,
		notifications,
		unreadCount,
		type Notification as NotificationType,
	} from '$lib/stores/notifications.svelte'
	import { isLoggedIn } from '$lib/stores/session.svelte'

	const chrome = useSystemChrome()

	let controlCenterEl: HTMLElement | null = $state(null)
	let controlCenterHeightPx = $state(0)

	function syncControlCenterHeight(): void {
		controlCenterHeightPx = controlCenterEl?.offsetHeight ?? 0
	}

	onMount(() => {
		if (isLoggedIn) {
			initNotifications()
		}

		syncControlCenterHeight()
		const ro = new ResizeObserver(() => syncControlCenterHeight())
		if (controlCenterEl) ro.observe(controlCenterEl)

		return () => ro.disconnect()
	})

	$effect(() => {
		if (isLoggedIn) {
			initNotifications()
		}
	})

	$effect(() => {
		const agentIds: string[] = []
		for (const notif of notifications) {
			const data = notif.event?.data as Record<string, unknown> | undefined
			const agentId = data && typeof data.agent_id === 'string' ? data.agent_id : null
			if (agentId) agentIds.push(agentId)
		}
		if (agentIds.length > 0) void ensureAgents(agentIds)
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
		return agentsById[agentId]?.profile_image_url ?? null
	}

	function handleMarkRead(notifId: string): void {
		void markNotificationRead(notifId)
	}

	function handleDismiss(notifId: string): void {
		void deleteNotification(notifId)
	}

	function handleMarkAllRead(): void {
		void markAllNotificationsRead()
	}
</script>

<aside class="relative h-full w-full" aria-hidden={!chrome.isDockOpen}>
	<div class="flex h-full flex-col gap-4">
		<section
			data-dock-panel
			class="blur-area rounded-container relative flex min-h-0 flex-col px-5 py-4"
			style={controlCenterHeightPx > 0
				? `max-height: calc(100% - ${controlCenterHeightPx}px - 1rem);`
				: undefined}
			aria-label="notifications"
		>
			<div class="flex min-h-0 flex-col">
				<div class="mb-2 flex items-center justify-between">
					<div class="text-xs font-semibold tracking-wide text-white/60">
						notifications
						{#if unreadCount > 0}
							<span
								class="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/15 px-1.5 text-[0.6875rem] font-bold text-white/80"
							>
								{unreadCount}
							</span>
						{/if}
					</div>
					{#if unreadCount > 0}
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
					{#if !isLoggedIn}
						<div
							class="rounded-2xl bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							log in to see notifications
						</div>
					{:else if notifications.length === 0}
						<div
							class="rounded-2xl bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							no notifications
						</div>
					{:else}
						{#each notifications as notif (notif.id)}
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
			class="blur-area rounded-container shrink-0 px-5 py-4"
			aria-label="control center"
			bind:this={controlCenterEl}
		>
			<div class="mb-3 text-xs font-semibold tracking-wide text-white/60">control center</div>

			<div class="grid grid-cols-2 gap-2">
				<button
					class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					wifi
				</button>
				<button
					class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					bluetooth
				</button>
				<button
					class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					focus
				</button>
				<button
					class="rounded-2xl border-none bg-white/5 px-3 py-3 text-left text-sm text-white/80 transition-all duration-150 hover:bg-white/8 active:scale-[0.99]"
					type="button"
				>
					dark mode
				</button>
			</div>
		</section>
	</div>
</aside>

<style>
	.blur-area {
		position: relative;
		isolation: isolate;
		overflow: visible; /* let the blur bleed out */
	}

	.blur-area::before {
		content: '';
		position: absolute;
		inset: -100px;
		pointer-events: none;
		z-index: 0;
		border-radius: 100px;

		backdrop-filter: blur(14px);
		-webkit-backdrop-filter: blur(14px);

		/* smoother eased ramp using multiple stops */
		-webkit-mask:
			linear-gradient(
				to right,
				transparent,
				rgba(0, 0, 0, 0.1) 25px,
				rgba(0, 0, 0, 0.4) 50px,
				rgba(0, 0, 0, 0.75) 75px,
				black 100px,
				black calc(100% - 100px),
				rgba(0, 0, 0, 0.75) calc(100% - 75px),
				rgba(0, 0, 0, 0.4) calc(100% - 50px),
				rgba(0, 0, 0, 0.1) calc(100% - 25px),
				transparent
			),
			linear-gradient(
				to bottom,
				transparent,
				rgba(0, 0, 0, 0.1) 25px,
				rgba(0, 0, 0, 0.4) 50px,
				rgba(0, 0, 0, 0.75) 75px,
				black 100px,
				black calc(100% - 100px),
				rgba(0, 0, 0, 0.75) calc(100% - 75px),
				rgba(0, 0, 0, 0.4) calc(100% - 50px),
				rgba(0, 0, 0, 0.1) calc(100% - 25px),
				transparent
			);
		-webkit-mask-composite: source-in;
		mask:
			linear-gradient(
				to right,
				transparent,
				rgba(0, 0, 0, 0.1) 25px,
				rgba(0, 0, 0, 0.4) 50px,
				rgba(0, 0, 0, 0.75) 75px,
				black 100px,
				black calc(100% - 100px),
				rgba(0, 0, 0, 0.75) calc(100% - 75px),
				rgba(0, 0, 0, 0.4) calc(100% - 50px),
				rgba(0, 0, 0, 0.1) calc(100% - 25px),
				transparent
			),
			linear-gradient(
				to bottom,
				transparent,
				rgba(0, 0, 0, 0.1) 25px,
				rgba(0, 0, 0, 0.4) 50px,
				rgba(0, 0, 0, 0.75) 75px,
				black 100px,
				black calc(100% - 100px),
				rgba(0, 0, 0, 0.75) calc(100% - 75px),
				rgba(0, 0, 0, 0.4) calc(100% - 50px),
				rgba(0, 0, 0, 0.1) calc(100% - 25px),
				transparent
			);
		mask-composite: intersect;
		transform: translateZ(0);
		-webkit-transform: translateZ(0);
		will-change: backdrop-filter;
		backface-visibility: hidden;
	}

	.blur-area > :global(*) {
		position: relative;
		z-index: 1;
	}
</style>
