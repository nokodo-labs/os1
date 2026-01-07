<script lang="ts">
	import '$lib/styles/liquid-glass.css'
	import { onMount } from 'svelte'
	import UserProfilePanel from './UserProfilePanel.svelte'

	interface UserProfileTriggerProps {
		user: {
			name: string
			email: string
			avatar?: string | null
		} | null
		isExpanded?: boolean
		placement?: 'sidebar' | 'header'
	}

	let { user, isExpanded = false, placement = 'sidebar' }: UserProfileTriggerProps = $props()

	let isOpen = $state(false)
	let buttonElement: HTMLButtonElement | undefined = $state()
	let panelElement: HTMLDivElement | undefined = $state()

	function getUserInitials(name: string): string {
		return name
			.split(' ')
			.map((n) => n[0])
			.join('')
			.toUpperCase()
			.slice(0, 2)
	}

	function togglePanel() {
		isOpen = !isOpen
	}

	function closePanel() {
		isOpen = false
	}

	function handleClickOutside(event: MouseEvent) {
		if (
			isOpen &&
			panelElement &&
			buttonElement &&
			!panelElement.contains(event.target as Node) &&
			!buttonElement.contains(event.target as Node)
		) {
			closePanel()
		}
	}

	onMount(() => {
		document.addEventListener('click', handleClickOutside)
		return () => {
			document.removeEventListener('click', handleClickOutside)
		}
	})
	const isHeaderPlacement = $derived(placement === 'header')
	const safeUser = $derived(user ?? { name: 'not signed in', email: '', avatar: null })
</script>

<div class="user-profile-trigger-container {isHeaderPlacement ? '' : 'mt-auto'}">
	<button
		bind:this={buttonElement}
		class="relative flex cursor-pointer items-center border border-transparent bg-transparent text-white transition-all duration-200 {isHeaderPlacement
			? 'h-12 w-12 justify-center p-0 hover:scale-[1.05] active:scale-[0.97]'
			: isExpanded
				? 'w-full justify-start gap-3 rounded-xl p-3 hover:border-white/10 hover:bg-white/5'
				: 'h-14 w-14 justify-center rounded-xl p-3 hover:border-white/10 hover:bg-white/5'}"
		onclick={togglePanel}
		aria-label="User Profile"
		aria-expanded={isOpen}
	>
		{#if safeUser.avatar}
			<img
				src={safeUser.avatar}
				alt={safeUser.name}
				class="{isExpanded
					? 'h-10 w-10'
					: 'h-9 w-9'} shrink-0 rounded-full transition-all duration-200"
			/>
		{:else}
			<div
				class="{isHeaderPlacement
					? 'h-10 w-10 text-[0.875rem]'
					: isExpanded
						? 'h-10 w-10 text-[0.875rem]'
						: 'h-9 w-9 text-[0.75rem]'} flex shrink-0 items-center justify-center rounded-full font-semibold text-white uppercase transition-all duration-200"
				style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-secondary));"
			>
				{getUserInitials(safeUser.name)}
			</div>
		{/if}
		{#if isExpanded}
			<div
				class="flex min-w-0 flex-col text-left opacity-0 transition-opacity delay-100 duration-300 {isExpanded
					? 'opacity-100'
					: ''}"
			>
				<p
					class="overflow-hidden text-sm font-semibold text-ellipsis whitespace-nowrap text-white"
				>
					{safeUser.name}
				</p>
				<p class="overflow-hidden text-xs text-ellipsis whitespace-nowrap text-white/60">
					{safeUser.email}
				</p>
			</div>
		{/if}
	</button>

	{#if isOpen}
		<div
			bind:this={panelElement}
			class="profile-panel-wrapper liquid-metal {isHeaderPlacement ? 'header' : ''}"
		>
			<UserProfilePanel {user} onClose={closePanel} />
		</div>
	{/if}
</div>

<style>
	.user-profile-trigger-container {
		position: relative;
	}

	.profile-panel-wrapper {
		position: absolute;
		bottom: 0;
		left: calc(100% + 0.5rem);
		z-index: 1000;
		border-radius: var(--radius-container-base);
		animation: fadeIn 0.15s ease-out;
	}

	.profile-panel-wrapper.header {
		top: calc(100% + 0.5rem);
		right: 0;
		bottom: auto;
		left: auto;
	}

	:global(.dark) .profile-panel-wrapper {
		border-color: rgba(255, 255, 255, 0.1);
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(4px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
