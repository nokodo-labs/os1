<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { ConfirmDeletePayload } from '$lib/stores/modals.svelte'

	interface Props {
		open: boolean
		payload: ConfirmDeletePayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	let isDeleting = $state(false)
	let error = $state<string | null>(null)

	async function runDelete(): Promise<void> {
		if (!payload) return
		isDeleting = true
		error = null
		try {
			const result = await payload.onDelete()
			if (result === false) {
				error = 'could not delete'
				return
			}
			onClose()
		} catch {
			error = 'could not delete'
		} finally {
			isDeleting = false
		}
	}

	function handleClose(): void {
		if (isDeleting) return
		error = null
		onClose()
	}

	$effect(() => {
		if (!open) {
			isDeleting = false
			error = null
		}
	})
</script>

<BaseModal
	{open}
	title={payload?.title ?? 'delete?'}
	description={payload?.description}
	onClose={handleClose}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		{#if error}
			<div
				class="rounded-container border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
			>
				{error}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
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
