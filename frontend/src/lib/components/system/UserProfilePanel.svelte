<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { logout } from '$lib/api/client'
	import { Cog6, QuestionMarkCircle, SignOut, Sparkles } from '$lib/components/icons'
	import { session } from '$lib/stores/session.svelte'

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
		void goto(resolve('/settings'), { keepFocus: true, noScroll: true })
	}

	function handlePersonalizeClick() {
		console.log('Open personalize')
		onClose?.()
		// TODO: navigate to personalization page or open modal
	}

	function handleHelpClick() {
		console.log('Open help')
		onClose?.()
		// TODO: open help modal or navigate to help page
	}

	function handleLogout() {
		onClose?.()
		void logout()
		session.clear()
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
			id: 'help',
			icon: QuestionMarkCircle,
			label: 'help & support',
			action: handleHelpClick,
		},
	]
</script>

<div class="w-80 p-4">
	<!-- User Info Section -->
	<div class="flex items-center gap-3 p-3">
		{#if session.isLoggedIn && user}
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

	<hr class="my-2 border-white/10" />

	{#if session.isLoggedIn}
		<!-- menu Items -->
		<div class="flex flex-col gap-1">
			{#each menuItems as item (item.id)}
				{@const Icon = item.icon}
				<button
					class="rounded-pill flex w-full cursor-pointer items-center gap-3 border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-white transition-all duration-150 hover:border-white/20 hover:bg-white/10 active:scale-[0.98]"
					onclick={item.action}
				>
					<Icon class="h-4.5 w-4.5 shrink-0" variant={item.variant} />
					<span>{item.label}</span>
				</button>
			{/each}
		</div>
	{:else}
		<div class="flex flex-col gap-1">
			<button
				class="rounded-pill flex w-full cursor-pointer items-center justify-center border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white transition-all duration-150 hover:bg-white/10 active:scale-[0.98]"
				onclick={handleLogin}
			>
				log in
			</button>
		</div>
	{/if}

	<hr class="my-2 border-white/10" />

	{#if session.isLoggedIn}
		<!-- logout Button -->
		<button
			class="rounded-pill flex w-full cursor-pointer items-center gap-3 border border-transparent bg-transparent px-4 py-3 text-left text-sm font-medium text-[rgb(239,68,68)] transition-all duration-150 hover:border-[rgba(239,68,68,0.3)] hover:bg-[rgba(239,68,68,0.15)] active:scale-[0.98]"
			onclick={handleLogout}
		>
			<SignOut class="h-4.5 w-4.5 shrink-0" />
			<span>log out</span>
		</button>
	{/if}
</div>
