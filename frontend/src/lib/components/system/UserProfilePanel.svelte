<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { logoutAndRedirect } from '$lib/auth/logout'
	import { ChevronRight, Cog6, InfoCircle, SignOut, Sparkles } from '$lib/components/icons'
	import { appNavigation } from '$lib/stores/appNavigation.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { getUserInitials } from '$lib/utils'

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

	interface MenuItem {
		id: string
		icon: IconComponent
		label: string
		action: () => void
		variant?: 'outline' | 'solid'
	}

	const menuItems: MenuItem[] = [
		{
			id: 'settings',
			icon: Cog6,
			label: 'settings',
			action: handleSettingsClick,
			variant: 'solid',
		},
		{
			id: 'personalize',
			icon: Sparkles,
			label: 'personalize',
			action: handlePersonalizeClick,
			variant: 'solid',
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
	<button
		class="flex w-full cursor-pointer items-center gap-2.5 rounded-xl px-2 py-1.5 text-left transition-transform active:scale-[0.98] disabled:cursor-default"
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
				<p
					class="text-foreground/60 overflow-hidden text-xs text-ellipsis whitespace-nowrap"
				>
					{user.email}
				</p>
			</div>
			<ChevronRight class="text-foreground/30 h-4 w-4 shrink-0" />
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

	<hr class="border-foreground/10 my-1.5" />

	{#if session.isLoggedIn}
		<!-- menu items -->
		<div class="flex flex-col gap-0.5">
			{#each menuItems as item (item.id)}
				{@const Icon = item.icon}
				<button
					class="rounded-pill text-foreground hover:border-foreground/20 hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-2.5 border border-transparent bg-transparent px-3 py-2 text-left text-sm font-semibold transition-all duration-150 active:scale-[0.98]"
					onclick={item.action}
				>
					<Icon class="h-4 w-4 shrink-0" variant={item.variant} />
					<span>{item.label}</span>
				</button>
			{/each}
		</div>
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

	<hr class="border-foreground/10 my-1.5" />

	{#if session.isLoggedIn}
		<!-- logout button -->
		<button
			class="rounded-pill flex w-full cursor-pointer items-center gap-2.5 border border-transparent bg-transparent px-3 py-2 text-left text-sm font-semibold text-[rgb(239,68,68)] transition-all duration-150 hover:border-[rgba(239,68,68,0.3)] hover:bg-[rgba(239,68,68,0.15)] active:scale-[0.98]"
			onclick={handleLogout}
			disabled={isLoggingOut}
		>
			<SignOut class="h-4 w-4 shrink-0" />
			<span>log out</span>
		</button>
	{/if}
</div>
