<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	interface Props {
		open: boolean
		thread: Thread | null
		title: string
		tagsCsv: string
		error: string | null
		isSaving: boolean
		onClose: () => void
		onCancel: () => void
		onSave: () => void
	}

	let {
		open,
		thread,
		title = $bindable(),
		tagsCsv = $bindable(),
		error,
		isSaving,
		onClose,
		onCancel,
		onSave,
	}: Props = $props()
</script>

<BaseModal
	{open}
	title="edit chat"
	description="placeholder - wiring to the API comes next"
	{onClose}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		<div class="space-y-3">
			<label class="block">
				<div class="text-foreground/60 text-xs font-semibold uppercase">title</div>
				<input
					class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 mt-1 w-full border px-3 py-2 text-sm outline-hidden"
					bind:value={title}
					placeholder={thread?.title ? thread.title : 'untitled chat'}
					disabled={isSaving}
				/>
			</label>
			<label class="block">
				<div class="text-foreground/60 text-xs font-semibold uppercase">tags</div>
				<input
					class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 placeholder:text-foreground/40 mt-1 w-full border px-3 py-2 text-sm outline-hidden"
					bind:value={tagsCsv}
					placeholder="comma, separated, tags"
					disabled={isSaving}
				/>
			</label>
		</div>

		{#if error}
			<div
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/70 border px-3 py-2 text-sm"
			>
				{error}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
			<button
				type="button"
				class="rounded-pill border-foreground/10 text-foreground/80 hover:bg-foreground/5 border bg-transparent px-4 py-2 text-sm transition-colors duration-150"
				disabled={isSaving}
				onclick={onCancel}
			>
				cancel
			</button>
			<button
				type="button"
				class="rounded-pill border-foreground/10 bg-foreground/10 text-foreground/90 hover:bg-foreground/15 border px-4 py-2 text-sm transition-colors duration-150 disabled:opacity-60"
				disabled={isSaving}
				onclick={onSave}
			>
				{#if isSaving}
					<ShimmerText className="inline-block">saving</ShimmerText>
				{:else}
					save
				{/if}
			</button>
		</div>
	</div>
</BaseModal>
