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
	description="placeholder — wiring to the API comes next"
	{onClose}
	widthClassName="max-w-sm"
>
	<div class="space-y-4">
		<div class="space-y-3">
			<label class="block">
				<div class="text-xs font-semibold text-white/60 uppercase">title</div>
				<input
					class="rounded-pill mt-1 w-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 outline-hidden placeholder:text-white/30"
					bind:value={title}
					placeholder={thread?.title ? thread.title : 'untitled chat'}
					disabled={isSaving}
				/>
			</label>
			<label class="block">
				<div class="text-xs font-semibold text-white/60 uppercase">tags</div>
				<input
					class="rounded-pill mt-1 w-full border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/90 outline-hidden placeholder:text-white/30"
					bind:value={tagsCsv}
					placeholder="comma, separated, tags"
					disabled={isSaving}
				/>
			</label>
		</div>

		{#if error}
			<div
				class="rounded-pill border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
			>
				{error}
			</div>
		{/if}

		<div class="flex items-center justify-end gap-2">
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
				disabled={isSaving}
				onclick={onCancel}
			>
				cancel
			</button>
			<button
				type="button"
				class="rounded-pill border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/90 transition-colors duration-150 hover:bg-white/15 disabled:opacity-60"
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
