<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Bell from '$lib/components/icons/Bell.svelte'
	import BellSlash from '$lib/components/icons/BellSlash.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import ChevronUp from '$lib/components/icons/ChevronUp.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import Map from '$lib/components/icons/Map.svelte'
	import Moon from '$lib/components/icons/Moon.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Sun from '$lib/components/icons/Sun.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import Notification from '$lib/components/system/Notification.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { useTheme, type ThemeMode } from '$lib/contexts/themeContext.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import {
		notifications,
		type Notification as NotificationType,
	} from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import SvelteVirtualList from '@humanspeak/svelte-virtual-list'
	import type { Component } from 'svelte'
	import { cubicOut } from 'svelte/easing'
	import { slide } from 'svelte/transition'

	const chrome = useSystemChrome()
	const theme = useTheme()

	// local toggle states (visual only)
	let isDnD = $state(false)
	let isLocationOn = $state(false)
	let isAppearOffline = $state(false)
	let isCCExpanded = $state(false)
	let isManaging = $state(false)

	type QuickActionId = 'dnd' | 'theme' | 'location' | 'offline'
	let quickActionOrder = $state<QuickActionId[]>(['dnd', 'theme', 'location', 'offline'])

	type DockNotificationRow =
		| { kind: 'notification'; id: string; notification: NotificationType }
		| { kind: 'dismiss-all'; id: 'dismiss-all' }

	const notificationRows = $derived.by((): DockNotificationRow[] => {
		const rows: DockNotificationRow[] = notifications.list.map((notification) => ({
			kind: 'notification',
			id: notification.id,
			notification,
		}))
		if (notifications.list.length > 0) rows.push({ kind: 'dismiss-all', id: 'dismiss-all' })
		return rows
	})

	// -- notification lifecycle --

	$effect(() => {
		if (session.isLoggedIn) notifications.init()
		else notifications.cleanup()
	})

	$effect(() => {
		if (chrome.isDockOpen && session.isLoggedIn && notifications.unreadCount > 0) {
			void notifications.markAllRead()
		}
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

	// -- notification helpers --

	function getNotificationTitle(notif: NotificationType): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return notif.title || (data?.title as string) || notif.event?.type || 'notification'
	}

	function getNotificationBody(notif: NotificationType): string {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return notif.body || (data?.body as string) || ''
	}

	function getNotificationIcon(notif: NotificationType): string | null {
		const data = notif.event?.data as Record<string, unknown> | undefined
		const explicit =
			notif.icon_url || (data && typeof data.icon_url === 'string' ? data.icon_url : null)
		if (explicit) return explicit
		const agentId = data && typeof data.agent_id === 'string' ? data.agent_id : null
		if (!agentId) return null
		return agents.get(agentId)?.profile_image_url ?? null
	}

	function getNotificationImage(notif: NotificationType): string | null {
		const data = notif.event?.data as Record<string, unknown> | undefined
		return (
			notif.image_url || (data && typeof data.image_url === 'string' ? data.image_url : null)
		)
	}

	function handleMarkRead(notifId: string): void {
		void notifications.markRead(notifId)
	}
	function handleDismiss(notifId: string): void {
		void notifications.delete(notifId)
	}
	function handleDismissAll(): void {
		void notifications.dismissAll()
	}

	// -- quick action helpers --

	function toggleAction(id: QuickActionId): void {
		if (id === 'dnd') isDnD = !isDnD
		else if (id === 'theme') cycleTheme()
		else if (id === 'location') isLocationOn = !isLocationOn
		else if (id === 'offline') isAppearOffline = !isAppearOffline
	}

	function cycleTheme(): void {
		const modes: ThemeMode[] = ['auto', 'light', 'dark']
		const idx = modes.indexOf(theme.mode)
		theme.setMode(modes[(idx + 1) % modes.length])
	}

	function setThemeMode(mode: ThemeMode): void {
		theme.setMode(mode)
	}

	function isActionActive(id: QuickActionId): boolean {
		if (id === 'dnd') return isDnD
		if (id === 'theme') return theme.mode !== 'auto'
		if (id === 'location') return isLocationOn
		if (id === 'offline') return isAppearOffline
		return false
	}

	type IconComp = Component<{ class?: string }>

	function getActionIcon(id: QuickActionId): IconComp {
		if (id === 'dnd') return isDnD ? (BellSlash as IconComp) : (Bell as IconComp)
		if (id === 'theme') {
			if (theme.mode === 'light') return Sun as IconComp
			if (theme.mode === 'dark') return Moon as IconComp
			return Sparkles as IconComp
		}
		if (id === 'location') return Map as IconComp
		if (id === 'offline') return isAppearOffline ? (EyeSlash as IconComp) : (Eye as IconComp)
		return Bell as IconComp
	}

	function getActionLabel(id: QuickActionId): string {
		if (id === 'dnd') return isDnD ? 'focus mode' : 'focus'
		if (id === 'theme') return theme.mode
		if (id === 'location') return 'location'
		if (id === 'offline') return isAppearOffline ? 'appear offline' : 'online'
		return id
	}

	function moveActionUp(idx: number): void {
		if (idx === 0) return
		const arr = [...quickActionOrder]
		;[arr[idx - 1], arr[idx]] = [arr[idx], arr[idx - 1]]
		quickActionOrder = arr
	}

	function moveActionDown(idx: number): void {
		if (idx >= quickActionOrder.length - 1) return
		const arr = [...quickActionOrder]
		;[arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]]
		quickActionOrder = arr
	}

	function toggleCC(): void {
		isCCExpanded = !isCCExpanded
		if (!isCCExpanded) isManaging = false
	}
</script>

<aside class="relative h-full w-full" inert={!chrome.isDockOpen}>
	<div class="flex h-full flex-col gap-3" data-dock-panel>
		<!-- notifications -->
		<div class="flex min-h-0 flex-1 flex-col overflow-hidden">
			<div class="flex shrink-0 items-center justify-between px-3 pb-2">
				<button
					type="button"
					class="text-foreground relative flex h-12 w-12 shrink-0 cursor-pointer items-center justify-center rounded-full border border-transparent bg-transparent transition-all"
					onclick={() => chrome.closeDock()}
					aria-label="close dock"
				>
					<ChevronRight class="h-8 w-8" />
				</button>

				<div
					class="text-foreground/70 flex min-w-0 items-center justify-end text-sm font-semibold"
				>
					notifications
					{#if notifications.unreadCount > 0}
						<span
							class="text-foreground ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-(--accent-primary)/20 px-1.5 text-xs font-bold"
						>
							{notifications.unreadCount}
						</span>
					{/if}
				</div>
			</div>

			<div class="dock-notifications-rule" aria-hidden="true"></div>

			<div class="relative min-h-0 flex-1 overflow-hidden" aria-label="notifications">
				{#if !session.isLoggedIn}
					<EmptyState label="log in to see notifications" compact class="h-full" />
				{:else if notifications.list.length === 0}
					<EmptyState label="no notifications" compact class="h-full" />
				{:else}
					<SvelteVirtualList
						items={notificationRows}
						defaultEstimatedItemHeight={96}
						bufferSize={10}
						containerClass="relative h-full min-h-0 w-full overflow-hidden"
						viewportClass="dock-notifications-scroll absolute inset-0 w-full overflow-y-auto"
						contentClass="relative min-h-full w-full"
						itemsClass="absolute top-0 left-0 flex w-full flex-col gap-2 px-3 py-2"
					>
						{#snippet renderItem(row)}
							{#if row.kind === 'notification'}
								{@const notif = row.notification}
								<Notification
									notification={notif}
									iconUrl={getNotificationIcon(notif)}
									imageUrl={getNotificationImage(notif)}
									title={getNotificationTitle(notif)}
									body={getNotificationBody(notif)}
									timestamp={new Date(notif.created_at)}
									isUnread={!notif.read_at}
									onMarkRead={handleMarkRead}
									onDismiss={handleDismiss}
								/>
							{:else}
								<div class="pt-1">
									<button
										type="button"
										class="interactive-subtle text-muted-foreground hover:text-foreground/80 flex w-full items-center justify-center gap-1.5 py-2 text-xs"
										onclick={handleDismissAll}
									>
										<XMark class="h-3.5 w-3.5" />
										dismiss all
									</button>
								</div>
							{/if}
						{/snippet}
					</SvelteVirtualList>
				{/if}
			</div>

			<div class="dock-notifications-rule" aria-hidden="true"></div>
		</div>

		<!-- control center (android quick settings style) -->
		<section
			class="dock-control-center rounded-popup bg-muted/15 shrink-0 overflow-hidden"
			data-dock-panel
			aria-label="control center"
		>
			<!-- header -->
			<div class="flex items-center justify-between px-5 pt-4 pb-3">
				<div class="text-foreground/70 text-sm font-semibold">control center</div>
				<div class="flex items-center gap-1">
					{#if isCCExpanded}
						<button
							type="button"
							class="interactive flex h-7 w-7 items-center justify-center rounded-full transition-all
								{isManaging
								? 'bg-foreground text-background'
								: 'text-foreground/50 hover:bg-muted/30 hover:text-foreground/80'}"
							aria-label="manage quick actions"
							aria-pressed={isManaging}
							onclick={() => (isManaging = !isManaging)}
						>
							<Pencil class="h-4 w-4" />
						</button>
					{/if}
					<button
						type="button"
						class="interactive text-foreground/50 hover:bg-muted/30 hover:text-foreground/80 flex h-7 w-7 items-center justify-center rounded-full transition-colors"
						aria-label={isCCExpanded
							? 'collapse control center'
							: 'expand control center'}
						onclick={toggleCC}
					>
						<ChevronUp
							class="h-4 w-4 transition-transform duration-300 {isCCExpanded
								? 'rotate-180'
								: ''}"
						/>
					</button>
				</div>
			</div>

			<!-- quick action tiles or manage mode -->
			{#if !isManaging}
				<div class="grid grid-cols-2 gap-2 px-4 pb-4">
					{#each quickActionOrder as actionId (actionId)}
						{@const active = isActionActive(actionId)}
						{@const ActionIcon = getActionIcon(actionId)}
						<button
							type="button"
							class="interactive rounded-popup flex items-center gap-3 px-4 py-3 transition-colors
								{active
								? 'text-foreground bg-(--accent-primary)/15'
								: 'bg-muted/15 text-foreground/60 hover:bg-muted/25'}"
							onclick={() => toggleAction(actionId)}
						>
							<ActionIcon class="h-5 w-5 shrink-0" />
							<span class="text-sm {active ? 'font-semibold' : 'font-medium'}">
								{getActionLabel(actionId)}
							</span>
						</button>
					{/each}
				</div>
			{:else}
				<!-- manage: reorder tiles -->
				<div class="px-4 pb-4">
					<p class="text-muted-foreground/60 mb-2 text-xs">reorder quick actions</p>
					<div class="flex flex-col gap-1.5">
						{#each quickActionOrder as actionId, idx (actionId)}
							{@const ActionIcon = getActionIcon(actionId)}
							<div
								class="rounded-popup bg-muted/15 flex items-center gap-3 px-4 py-2.5"
							>
								<ActionIcon class="text-foreground/50 h-4.5 w-4.5 shrink-0" />
								<span class="text-foreground/70 flex-1 text-sm font-medium">
									{getActionLabel(actionId)}
								</span>
								<div class="flex items-center gap-0.5">
									<button
										type="button"
										class="interactive text-foreground/40 hover:bg-muted/30 hover:text-foreground/70 flex h-6 w-6 items-center justify-center rounded disabled:cursor-not-allowed disabled:opacity-20"
										disabled={idx === 0}
										onclick={() => moveActionUp(idx)}
										aria-label="move up"
									>
										<ChevronUp class="h-3.5 w-3.5" />
									</button>
									<button
										type="button"
										class="interactive text-foreground/40 hover:bg-muted/30 hover:text-foreground/70 flex h-6 w-6 items-center justify-center rounded disabled:cursor-not-allowed disabled:opacity-20"
										disabled={idx >= quickActionOrder.length - 1}
										onclick={() => moveActionDown(idx)}
										aria-label="move down"
									>
										<ChevronDown class="h-3.5 w-3.5" />
									</button>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- expanded: appearance mode picker (slides in below tiles) -->
			{#if isCCExpanded && !isManaging}
				<div class="px-4 pb-4" transition:slide={{ duration: 250, easing: cubicOut }}>
					<div class="rounded-popup bg-muted/15 p-3">
						<div
							class="text-muted-foreground/60 mb-2 text-xs font-semibold tracking-wider uppercase"
						>
							appearance
						</div>
						<div class="grid grid-cols-3 gap-1.5">
							{#each ['auto', 'light', 'dark'] as ThemeMode[] as modeOpt (modeOpt)}
								{@const isSelected = theme.mode === modeOpt}
								<button
									type="button"
									class="interactive rounded-popup flex flex-col items-center gap-1.5 py-3
										{isSelected
										? 'text-foreground ring-border bg-(--accent-primary)/15 ring-1 ring-inset'
										: 'bg-muted/10 text-foreground/50 hover:bg-muted/20 hover:text-foreground/70'}"
									onclick={() => setThemeMode(modeOpt)}
								>
									{#if modeOpt === 'auto'}
										<Sparkles class="h-5 w-5" />
									{:else if modeOpt === 'light'}
										<Sun class="h-5 w-5" />
									{:else}
										<Moon class="h-5 w-5" />
									{/if}
									<span
										class="text-xs {isSelected
											? 'font-semibold'
											: 'font-medium'}"
									>
										{modeOpt}
									</span>
								</button>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</section>
	</div>
</aside>

<style>
	.dock-notifications-rule {
		height: 1px;
		width: 100%;
		background: linear-gradient(
			90deg,
			transparent,
			color-mix(in oklch, var(--foreground) 18%, transparent),
			transparent
		);
	}

	.dock-control-center {
		margin-right: 0.75rem;
		margin-left: 0.75rem;
	}
</style>
