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
	}

	let { user }: UserProfileTriggerProps = $props()

	let isOpen = $state(false)
	let buttonElement: HTMLButtonElement | undefined = $state()

	function togglePanel() {
		isOpen = !isOpen
	}

	function closePanel() {
		isOpen = false
	}

	const safeUser = $derived(user ?? { name: 'not signed in', email: '', avatar: null })
	const wsStatus = $derived(eventStreamClient.state.status)
</script>

<div class="user-profile-trigger-container">
	<button
		bind:this={buttonElement}
		class="text-foreground relative flex h-full w-12 cursor-pointer items-center justify-center border border-transparent bg-transparent px-0 transition-all duration-200 hover:scale-[1.05] active:scale-[0.97]"
		onclick={togglePanel}
		aria-label="User Profile"
		aria-expanded={isOpen}
	>
		<span class="relative inline-flex shrink-0" style="--avatar-size: 2.5rem;">
			{#if safeUser.avatar}
				<img
					src={safeUser.avatar}
					alt={safeUser.name}
					class="h-9 w-9 shrink-0 rounded-full transition-all duration-200"
				/>
			{:else}
				<div
					class="text-foreground flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[0.875rem] font-semibold uppercase transition-all duration-200"
					style="background: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
				>
					{getUserInitials(safeUser.name)}
				</div>
			{/if}
			<ConnectionIndicator status={wsStatus} />
		</span>
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
