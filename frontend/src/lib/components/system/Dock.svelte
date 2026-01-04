<script lang="ts">
	import { onMount } from 'svelte'

	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import {
		deleteNotification,
		initNotifications,
		markAllNotificationsRead,
		markNotificationRead,
		notifications,
		unreadCount,
		type Notification,
	} from '$lib/stores/notifications'
	import { isLoggedIn } from '$lib/stores/session'

	const chrome = useSystemChrome()

	onMount(() => {
		if ($isLoggedIn) {
			initNotifications()
		}
	})

	$effect(() => {
		if ($isLoggedIn) {
			initNotifications()
		}
	})

	function getNotificationTitle(notif: Notification): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (data?.title as string) || notif.event?.type || 'notification'
	}

	function getNotificationBody(notif: Notification): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (data?.body as string) || ''
	}

	function getNotificationIcon(notif: Notification): string | null {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (data?.icon_url as string) || null
	}

	function formatTime(iso: string): string {
		const date = new Date(iso)
		if (Number.isNaN(date.getTime())) return ''
		const now = Date.now()
		const diff = now - date.getTime()
		const minutes = Math.floor(diff / 60000)
		if (minutes < 1) return 'just now'
		if (minutes < 60) return `${minutes}m ago`
		const hours = Math.floor(minutes / 60)
		if (hours < 24) return `${hours}h ago`
		return date.toLocaleDateString()
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
			class="liquid-glass rounded-container px-5 py-4 shadow-[0_24px_48px_rgba(12,10,30,0.45)]"
			aria-label="notifications"
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="mb-2 flex items-center justify-between">
					<div class="text-xs font-semibold tracking-wide text-white/60">
						notifications
						{#if $unreadCount > 0}
							<span
								class="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/15 px-1.5 text-[0.6875rem] font-bold text-white/80"
							>
								{$unreadCount}
							</span>
						{/if}
					</div>
					{#if $unreadCount > 0}
						<button
							type="button"
							class="text-xs text-white/50 transition-colors hover:text-white/80"
							onclick={handleMarkAllRead}
						>
							mark all read
						</button>
					{/if}
				</div>
				<div class="flex max-h-80 flex-col gap-2 overflow-y-auto">
					{#if !$isLoggedIn}
						<div
							class="rounded-2xl bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							log in to see notifications
						</div>
					{:else if $notifications.length === 0}
						<div
							class="rounded-2xl bg-white/5 px-3 py-3 text-center text-sm text-white/50"
						>
							no notifications
						</div>
					{:else}
						{#each $notifications as notif (notif.id)}
							{@const iconUrl = getNotificationIcon(notif)}
							{@const isUnread = !notif.read_at}
							<div
								class="group relative flex items-start gap-3 rounded-2xl px-3 py-3 text-left transition-all duration-150 {isUnread
									? 'bg-white/8'
									: 'bg-white/3'} hover:bg-white/10"
							>
								<div
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/8 text-white/85"
								>
									{#if iconUrl}
										<img
											src={iconUrl}
											alt=""
											class="h-5 w-5 rounded-full object-cover"
										/>
									{:else}
										<AppNotification className="h-5 w-5" />
									{/if}
								</div>
								<div class="min-w-0 flex-1">
									<div
										class="flex items-center gap-2 text-[0.8125rem] font-semibold {isUnread
											? 'text-white/90'
											: 'text-white/70'}"
									>
										{getNotificationTitle(notif)}
										{#if isUnread}
											<span class="h-1.5 w-1.5 rounded-full bg-blue-400"
											></span>
										{/if}
									</div>
									<div
										class="truncate text-[0.8125rem] {isUnread
											? 'text-white/60'
											: 'text-white/45'}"
									>
										{getNotificationBody(notif)}
									</div>
									<div class="mt-1 text-[0.6875rem] text-white/40">
										{formatTime(notif.created_at)}
									</div>
								</div>
								<div
									class="absolute top-2 right-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100"
								>
									{#if isUnread}
										<button
											type="button"
											class="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white/60 transition-colors hover:bg-white/20 hover:text-white/90"
											title="mark as read"
											onclick={() => handleMarkRead(notif.id)}
										>
											<Check className="h-3 w-3" />
										</button>
									{/if}
									<button
										type="button"
										class="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-white/60 transition-colors hover:bg-white/20 hover:text-white/90"
										title="dismiss"
										onclick={() => handleDismiss(notif.id)}
									>
										<XMark className="h-3 w-3" />
									</button>
								</div>
							</div>
						{/each}
					{/if}
				</div>
			</div>
		</section>

		<div class="flex-1"></div>

		<section
			data-dock-panel
			class="liquid-glass rounded-container px-5 py-4 shadow-[0_24px_48px_rgba(12,10,30,0.45)]"
			aria-label="control center"
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="mb-3 text-xs font-semibold tracking-wide text-white/60">
					control center
				</div>

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
			</div>
		</section>
	</div>
</aside>
