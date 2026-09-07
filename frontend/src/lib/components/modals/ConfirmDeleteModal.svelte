<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ModalActions from '$lib/components/modals/ModalActions.svelte'
	import { Switch } from '$lib/components/primitives'
	import type { ConfirmDeletePayload } from '$lib/stores/modals.svelte'

	interface Props {
		open: boolean
		payload: ConfirmDeletePayload | null
		onClose: () => void
	}

	let { open, payload, onClose }: Props = $props()

	let isDeleting = $state(false)
	let error = $state<string | null>(null)
	// each dialog starts from its own toggle default, never a leftover choice.
	let toggleOn = $derived(payload?.toggle?.default ?? false)

	// not every confirmed action is a deletion; the caller names its own verb.
	const confirmLabel = $derived(payload?.confirmLabel ?? 'delete')
	const pendingLabel = $derived(payload?.pendingLabel ?? 'deleting')
	const ConfirmIcon = $derived(payload?.confirmIcon ?? Trash)

	async function runDelete(): Promise<void> {
		if (!payload || isDeleting) return
		isDeleting = true
		error = null
		try {
			const result = await payload.onDelete(toggleOn)
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

		{#if payload?.toggle}
			<div
				class="rounded-container liquid-glass liquid-glass--frosted border-foreground/10 bg-foreground/4 flex items-start justify-between gap-4 border p-4"
			>
				<div class="min-w-0">
					<div
						id="confirm-delete-toggle-label"
						class="text-foreground/85 text-sm font-medium"
					>
						{payload.toggle.label}
					</div>
					{#if payload.toggle.description}
						<div class="text-foreground/55 mt-1 text-sm">
							{payload.toggle.description}
						</div>
					{/if}
				</div>
				<Switch
					size="md"
					checked={toggleOn}
					onchange={(next) => (toggleOn = next)}
					disabled={isDeleting}
					ariaLabelledbyId="confirm-delete-toggle-label"
				/>
			</div>
		{/if}

		<ModalActions>
			<button
				type="button"
				class="rounded-pill inline-flex cursor-pointer items-center border border-red-500/25 bg-red-500/20 px-4 py-2 text-sm text-red-100 transition-colors duration-150 hover:bg-red-500/30 disabled:cursor-not-allowed disabled:opacity-60"
				disabled={isDeleting}
				onclick={() => void runDelete()}
			>
				<ConfirmIcon class="h-4 w-4" />
				<span class="ml-2">
					{#if isDeleting}
						<ShimmerText className="inline-block">{pendingLabel}</ShimmerText>
					{:else}
						{confirmLabel}
					{/if}
				</span>
			</button>
		</ModalActions>
	</div>
</BaseModal>
