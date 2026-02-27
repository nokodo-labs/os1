<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'

	export type DeleteModalText = {
		title: string
		description?: string
	}

	interface Props {
		confirm?: boolean
		modalText?: DeleteModalText
		onDelete: () => void | boolean | Promise<void | boolean>
		label?: string
		onTrigger?: () => void
		stopPropagation?: boolean
		showTrigger?: boolean
		open?: boolean
	}

	let {
		confirm = true,
		modalText = { title: 'delete?' },
		onDelete,
		label = 'delete',
		onTrigger,
		stopPropagation = false,
		showTrigger = true,
		open = $bindable(false),
	}: Props = $props()

	let isDeleting = $state(false)
	let error = $state<string | null>(null)

	async function runDelete(): Promise<void> {
		isDeleting = true
		error = null
		try {
			const result = await onDelete()
			if (result === false) {
				error = 'could not delete'
				return
			}
			open = false
		} catch {
			error = 'could not delete'
		} finally {
			isDeleting = false
		}
	}

	function handleTriggerClick(event: MouseEvent): void {
		if (stopPropagation) event.stopPropagation()
		onTrigger?.()
		if (confirm) {
			open = true
			return
		}
		void runDelete()
	}
</script>

{#if showTrigger}
	<button
		type="button"
		class="group rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
		onclick={handleTriggerClick}
	>
		<Trash
			class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover:text-red-300"
		/>
		<span class="ml-2">{label}</span>
	</button>
{/if}

<BaseModal
	{open}
	title={modalText.title}
	description={modalText.description}
	onClose={() => {
		if (isDeleting) return
		open = false
		error = null
	}}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		{#if error}
			<div
				class="rounded-container border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
			>
				{error}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
				disabled={isDeleting}
				onclick={() => {
					open = false
					error = null
				}}
			>
				cancel
			</button>
			<button
				type="button"
				class="rounded-pill inline-flex items-center border border-red-500/25 bg-red-500/20 px-4 py-2 text-sm text-red-100 transition-colors duration-150 hover:bg-red-500/30 disabled:opacity-60"
				disabled={isDeleting}
				onclick={() => void runDelete()}
			>
				<Trash class="h-4 w-4" />
				<span class="ml-2">
					{#if isDeleting}
						<ShimmerText className="inline-block">deleting</ShimmerText>
					{:else}
						delete
					{/if}
				</span>
			</button>
		</div>
	</div>
</BaseModal>
