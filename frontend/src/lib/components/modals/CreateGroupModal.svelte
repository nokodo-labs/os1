<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import UserGroup from '$lib/components/icons/UserGroup.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { groups } from '$lib/stores/groups.svelte'

	interface CreateGroupModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: CreateGroupModalProps = $props()

	let name = $state('')
	let isCreating = $state(false)

	async function handleCreate() {
		const trimmed = name.trim()
		if (!trimmed) return
		isCreating = true
		const created = await groups.create({ name: trimmed })
		isCreating = false
		if (created) {
			name = ''
			onClose()
			void groups.load({ force: true })
		}
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault()
			handleCreate()
		}
	}

	$effect(() => {
		if (!open) {
			name = ''
			isCreating = false
		}
	})
</script>

<BaseModal
	{open}
	title="new group"
	description="create a group to collaborate with others"
	{onClose}
>
	<div class="flex flex-col gap-5">
		<div class="flex items-center gap-4">
			<div
				class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-(--accent-primary)/10"
			>
				<UserGroup class="h-7 w-7 text-(--accent-primary)" variant="solid" />
			</div>
			<input
				class="min-w-0 flex-1 rounded-full bg-foreground/8 px-4 py-3 text-sm text-foreground ring-1 ring-foreground/10 transition-all outline-none placeholder:text-foreground/30 focus:ring-(--accent-primary)/50"
				type="text"
				placeholder="group name"
				bind:value={name}
				onkeydown={handleKeyDown}
				disabled={isCreating}
			/>
		</div>

		<button
			class="interactive w-full rounded-full bg-(--accent-primary)/20 py-3 text-sm font-medium text-(--accent-primary) hover:bg-(--accent-primary)/30 disabled:pointer-events-none disabled:opacity-50"
			type="button"
			onclick={handleCreate}
			disabled={!name.trim() || isCreating}
		>
			{#if isCreating}
				<ShimmerText>creating</ShimmerText>
			{:else}
				create group
			{/if}
		</button>
	</div>
</BaseModal>
