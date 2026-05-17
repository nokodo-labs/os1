<script lang="ts">
	import { eventStreamClient } from '$lib/api/streaming'
	import { PopupMenu } from '$lib/components/primitives'
	import { getUserInitials } from '$lib/utils'
	import ConnectionIndicator from './ConnectionIndicator.svelte'
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

	function togglePanel() {
		isOpen = !isOpen
	}

	function closePanel() {
		isOpen = false
	}

	const isHeaderPlacement = $derived(placement === 'header')
	const safeUser = $derived(user ?? { name: 'not signed in', email: '', avatar: null })
	const wsStatus = $derived(eventStreamClient.state.status)
</script>

<div class="user-profile-trigger-container {isHeaderPlacement ? '' : 'mt-auto'}">
	<button
		bind:this={buttonElement}
		class="text-foreground relative flex cursor-pointer items-center border border-transparent bg-transparent transition-all duration-200 {isHeaderPlacement
			? 'h-full w-12 justify-center px-0 hover:scale-[1.05] active:scale-[0.97]'
			: isExpanded
				? 'rounded-pill hover:border-foreground/10 hover:bg-foreground/5 w-full justify-start gap-3 p-3'
				: 'rounded-pill hover:border-foreground/10 hover:bg-foreground/5 h-14 w-14 justify-center p-3'}"
		onclick={togglePanel}
		aria-label="User Profile"
		aria-expanded={isOpen}
	>
		<span
			class="relative inline-flex shrink-0"
			style={isHeaderPlacement ? '--avatar-size: 2.5rem;' : ''}
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
							: 'h-9 w-9 text-[0.75rem]'} text-foreground flex shrink-0 items-center justify-center rounded-full font-semibold uppercase transition-all duration-200"
					style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
				>
					{getUserInitials(safeUser.name)}
				</div>
			{/if}
			{#if isHeaderPlacement}
				<ConnectionIndicator status={wsStatus} />
			{/if}
		</span>
		{#if isExpanded}
			<div
				class="flex min-w-0 flex-col text-left opacity-0 transition-opacity delay-100 duration-300 {isExpanded
					? 'opacity-100'
					: ''}"
			>
				<p
					class="text-foreground overflow-hidden text-sm font-semibold text-ellipsis whitespace-nowrap"
				>
					{safeUser.name}
				</p>
				<p
					class="text-foreground/60 overflow-hidden text-xs text-ellipsis whitespace-nowrap"
				>
					{safeUser.email}
				</p>
			</div>
		{/if}
	</button>

	<PopupMenu open={isOpen} anchorEl={buttonElement ?? null} onClose={closePanel}>
		<UserProfilePanel {user} onClose={closePanel} />
	</PopupMenu>
</div>

<style>
	.user-profile-trigger-container {
		position: relative;
	}
</style>
