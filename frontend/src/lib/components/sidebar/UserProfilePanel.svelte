<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { logoutV1 } from '$lib/api/v1/client'
	import { Cog6, QuestionMarkCircle, SignOut, Sparkles } from '$lib/components/icons'
	import * as Separator from '$lib/components/ui/separator'
	import { openModal } from '$lib/stores/modals'
	import { clearSession, isLoggedIn } from '$lib/stores/session'

	interface UserProfilePanelProps {
		user: {
			name: string
			email: string
			avatar?: string | null
		} | null
		onClose?: () => void
	}

	let { user, onClose }: UserProfilePanelProps = $props()

	function handleSettingsClick() {
		onClose?.()
		openModal('settings')
	}

	function handlePersonalizeClick() {
		console.log('Open personalize')
		onClose?.()
		// TODO: Navigate to personalization page or open modal
	}

	function handleHelpClick() {
		console.log('Open help')
		onClose?.()
		// TODO: Open help modal or navigate to help page
	}

	function handleLogout() {
		onClose?.()
		void logoutV1()
		clearSession()
		void goto(resolve('/login'))
	}

	function handleLogin() {
		onClose?.()
		void goto(resolve('/login'))
	}

	function getUserInitials(name: string): string {
		return name
			.split(' ')
			.map((n) => n[0])
			.join('')
			.toUpperCase()
			.slice(0, 2)
	}

	type IconComponent = typeof Cog6

	interface MenuItem {
		id: string
		icon: IconComponent
		label: string
		action: () => void
	}

	const menuItems: MenuItem[] = [
		{
			id: 'settings',
			icon: Cog6,
			label: 'Settings',
			action: handleSettingsClick,
		},
		{
			id: 'personalize',
			icon: Sparkles,
			label: 'Personalize',
			action: handlePersonalizeClick,
		},
		{
			id: 'help',
			icon: QuestionMarkCircle,
			label: 'Help & Support',
			action: handleHelpClick,
		},
	]
</script>

<div class="w-80 p-4">
	<!-- User Info Section -->
	<div class="flex items-center gap-3 p-3">
		{#if $isLoggedIn && user}
			{#if user.avatar}
				<img
					src={user.avatar}
					alt={user.name}
					class="h-10 w-10 shrink-0 rounded-full object-cover"
				/>
			{:else}
				<div
					class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white uppercase"
					style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
				>
					{getUserInitials(user.name)}
				</div>
			{/if}
			<div class="flex min-w-0 flex-1 flex-col">
				<p
					class="overflow-hidden text-[0.9375rem] font-semibold text-ellipsis whitespace-nowrap text-white"
				>
					{user.name}
				</p>
				<p
					class="overflow-hidden text-[0.8125rem] text-ellipsis whitespace-nowrap text-white/60"
				>
					{user.email}
				</p>
			</div>
		{:else}
			<div
				class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white uppercase"
				style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
			>
				??
			</div>
			<div class="flex min-w-0 flex-1 flex-col">
				<p
					class="overflow-hidden text-[0.9375rem] font-semibold text-ellipsis whitespace-nowrap text-white"
				>
					not signed in
				</p>
				<p
					class="overflow-hidden text-[0.8125rem] text-ellipsis whitespace-nowrap text-white/60"
				>
					log in to access your account
				</p>
			</div>
		{/if}
	</div>

	<Separator.Root class="my-2 bg-white/10" />

	{#if $isLoggedIn}
		<!-- Menu Items -->
		<div class="flex flex-col gap-1">
			{#each menuItems as item (item.id)}
				{@const Icon = item.icon}
				<button
					class="flex w-full items-center gap-3 rounded-lg border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-white transition-all duration-150 hover:border-white/20 hover:bg-white/10 active:scale-[0.98]"
					onclick={item.action}
				>
					<Icon className="h-4.5 w-4.5 shrink-0" />
					<span>{item.label}</span>
				</button>
			{/each}
		</div>
	{:else}
		<div class="flex flex-col gap-1">
			<button
				class="flex w-full items-center justify-center rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition-all duration-150 hover:bg-white/10 active:scale-[0.98]"
				onclick={handleLogin}
			>
				log in
			</button>
		</div>
	{/if}

	<Separator.Root class="my-2 bg-white/10" />

	{#if $isLoggedIn}
		<!-- Logout Button -->
		<button
			class="flex w-full items-center gap-3 rounded-lg border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-[rgb(239,68,68)] transition-all duration-150 hover:border-[rgba(239,68,68,0.3)] hover:bg-[rgba(239,68,68,0.15)] active:scale-[0.98]"
			onclick={handleLogout}
		>
			<SignOut className="h-4.5 w-4.5 shrink-0" />
			<span>log out</span>
		</button>
	{/if}
</div>
