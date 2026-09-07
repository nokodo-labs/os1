<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { eventStreamClient } from '$lib/api/streaming'
	import { logoutAndRedirect } from '$lib/auth/logout'
	import {
		ArrowPath,
		ChevronRight,
		Cog6,
		InfoCircle,
		SignOut,
		Sparkles,
	} from '$lib/components/icons'
	import { MenuItem, MenuSeparator } from '$lib/components/primitives'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'
	import { onMount } from 'svelte'

	interface UserProfilePanelProps {
		user: {
			name: string
			email: string
			avatar?: string | null
		} | null
		onClose?: () => void
	}

	let { user, onClose }: UserProfilePanelProps = $props()
	let isLoggingOut = $state(false)

	// connection status
	const wsStatus = $derived(eventStreamClient.state.status)
	let now = $state(Date.now())
	onMount(() => {
		const id = setInterval(() => (now = Date.now()), 1000)
		return () => clearInterval(id)
	})
	const wsElapsed = $derived(
		eventStreamClient.state.statusSince === null ? 0 : now - eventStreamClient.state.statusSince
	)
	const wsConnected = $derived(wsStatus === 'connected')
	const wsErrored = $derived(wsStatus === 'disconnected')
	// offer a manual retry when the link is down OR stuck retrying (skips the
	// backoff wait), but not during the very first 'connecting' attempt.
	const wsCanRetry = $derived(wsStatus === 'disconnected' || wsStatus === 'reconnecting')
	const wsLabel = $derived(wsConnected ? 'connected' : wsErrored ? 'disconnected' : 'connecting')
	const wsDotColor = $derived(
		wsConnected ? 'bg-emerald-500' : wsErrored ? 'bg-red-500' : 'bg-amber-500'
	)
	const wsPingColor = $derived(
		wsConnected ? 'bg-emerald-400' : wsErrored ? 'bg-red-400' : 'bg-amber-400'
	)
	const wsTextColor = $derived(
		wsConnected ? 'text-emerald-400' : wsErrored ? 'text-red-400' : 'text-amber-400'
	)

	// a manual retry is "in flight" only for the connect attempt it kicks off;
	// once the status settles (connected, or back to reconnecting) it's done.
	let isRetrying = $state(false)
	$effect(() => {
		if (wsStatus !== 'connecting') isRetrying = false
	})

	function formatElapsed(ms: number): string {
		const totalSec = Math.max(0, Math.floor(ms / 1000))
		if (totalSec < 60) return `${totalSec}s`
		const minutes = Math.floor(totalSec / 60)
		const seconds = totalSec % 60
		if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
		const hours = Math.floor(minutes / 60)
		const mins = minutes % 60
		return mins ? `${hours}h ${mins}m` : `${hours}h`
	}

	function handleRetry() {
		isRetrying = true
		eventStreamClient.reconnect()
	}

	function handleUserProfileClick() {
		onClose?.()
		const userId = session.currentUser?.id
		if (userId) void goto(resolve(`/social/users/${userId}`))
	}

	function handleSettingsClick() {
		onClose?.()
		void goto(resolve(appNavigation.getEntryRoute('settings')), {
			keepFocus: true,
			noScroll: true,
		})
	}

	function handlePersonalizeClick() {
		onClose?.()
		void goto(resolve('/settings/ai'), { keepFocus: true, noScroll: true })
	}

	function handleAboutClick() {
		onClose?.()
		void goto(resolve('/settings/about'), { keepFocus: true, noScroll: true })
	}

	async function handleLogout() {
		if (isLoggingOut) return
		isLoggingOut = true
		onClose?.()
		try {
			await logoutAndRedirect()
		} finally {
			isLoggingOut = false
		}
	}

	function handleLogin() {
		onClose?.()
		void goto(resolve('/login'))
	}

	type IconComponent = typeof Cog6

	interface ProfileMenuEntry {
		id: string
		icon: IconComponent
		label: string
		action: () => void
	}

	const menuItems: ProfileMenuEntry[] = [
		{
			id: 'settings',
			icon: Cog6,
			label: 'settings',
			action: handleSettingsClick,
		},
		{
			id: 'personalize',
			icon: Sparkles,
			label: 'personalize',
			action: handlePersonalizeClick,
		},
		{
			id: 'about',
			icon: InfoCircle,
			label: 'about',
			action: handleAboutClick,
		},
	]
</script>

<div class="w-58 p-0">
	<!-- user info section (clickable to profile) -->
	<div class="flex w-full items-center gap-2.5 rounded-xl px-3 py-1.5">
		<button
			class="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5 text-left transition-transform active:scale-[0.98] disabled:cursor-default"
			onclick={handleUserProfileClick}
			disabled={!session.isLoggedIn}
		>
			{#if session.isLoggedIn && user}
				{#if user.avatar}
					<img
						src={user.avatar}
						alt={user.name}
						class="h-9 w-9 shrink-0 rounded-full object-cover"
					/>
				{:else}
					<div
						class="text-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold uppercase"
						style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
					>
						{getUserInitials(user.name)}
					</div>
				{/if}
				<div class="flex min-w-0 flex-1 flex-col">
					<p
						class="text-foreground overflow-hidden text-sm font-semibold text-ellipsis whitespace-nowrap"
					>
						{user.name}
					</p>
					<!-- connection status (in place of email) -->
					<span class="flex items-center gap-1.5">
						<span class="relative flex h-2 w-2 shrink-0">
							{#if !wsErrored}
								<span
									class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 {wsPingColor}"
								></span>
							{/if}
							<span class="relative inline-flex h-2 w-2 rounded-full {wsDotColor}"
							></span>
						</span>
						<span class="text-xs font-medium {wsTextColor}">{wsLabel}</span>
						{#if !wsConnected}
							<span class="text-foreground/40 text-xs tabular-nums"
								>{formatElapsed(wsElapsed)}</span
							>
						{/if}
					</span>
				</div>
				{#if !wsCanRetry && !isRetrying}
					<ChevronRight class="text-foreground/30 h-4 w-4 shrink-0" />
				{/if}
			{:else}
				<div
					class="text-foreground flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold uppercase"
					style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
				>
					??
				</div>
				<div class="flex min-w-0 flex-1 flex-col">
					<p
						class="text-foreground overflow-hidden text-sm font-semibold text-ellipsis whitespace-nowrap"
					>
						not signed in
					</p>
					<p
						class="text-foreground/60 overflow-hidden text-xs text-ellipsis whitespace-nowrap"
					>
						log in to access your account
					</p>
				</div>
			{/if}
		</button>
		{#if session.isLoggedIn && (wsCanRetry || isRetrying)}
			<button
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/80 hover:bg-foreground/10 flex shrink-0 cursor-pointer items-center gap-1 border px-2 py-0.5 text-xs font-medium transition-all duration-150 active:scale-[0.98] disabled:cursor-default disabled:active:scale-100"
				onclick={handleRetry}
				disabled={isRetrying}
			>
				<ArrowPath class="h-3 w-3 {isRetrying ? 'animate-spin' : ''}" />
				retry
			</button>
		{/if}
	</div>

	<MenuSeparator />

	{#if session.isLoggedIn}
		<!-- menu items -->
		{#each menuItems as item (item.id)}
			<MenuItem icon={item.icon} onclick={item.action}>{item.label}</MenuItem>
		{/each}
	{:else}
		<div class="flex flex-col gap-0.5">
			<button
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground hover:bg-foreground/10 flex w-full cursor-pointer items-center justify-center border px-4 py-2.5 text-sm font-semibold transition-all duration-150 active:scale-[0.98]"
				onclick={handleLogin}
			>
				log in
			</button>
		</div>
	{/if}

	<MenuSeparator />

	{#if session.isLoggedIn}
		<!-- logout button -->
		<MenuItem destructive icon={SignOut} onclick={handleLogout} disabled={isLoggingOut}>
			log out
		</MenuItem>
	{/if}
</div>
