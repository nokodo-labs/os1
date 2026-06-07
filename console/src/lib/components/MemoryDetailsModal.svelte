<script lang="ts">
	import { browser } from '$app/environment'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Memory = Schemas['Memory']
	type MemoryUpdate = Schemas['MemoryUpdate']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import { Save, Trash2, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		memoryId: string | null
		onUpdated?: (memory: Memory) => void
		onDeleted?: (memoryId: string) => void
		onClose?: () => void
	}

	let { open = $bindable(false), memoryId, onUpdated, onDeleted, onClose }: Props = $props()

	let memory = $state<Memory | null>(null)
	let isLoading = $state(false)
	let error = $state<string | null>(null)

	let editContent = $state('')
	let editTags = $state('')
	let editConfidence = $state('')
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)

	let confirmDelete = $state(false)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)

	function originalTags(m: Memory): string {
		return m.tags?.join(', ') ?? ''
	}

	function originalConfidence(m: Memory): string {
		return m.confidence !== null && m.confidence !== undefined
			? String((m.confidence * 100).toFixed(1))
			: ''
	}

	const isDirty = $derived(
		memory !== null &&
			(editContent !== memory.content ||
				editTags !== originalTags(memory) ||
				editConfidence !== originalConfidence(memory))
	)

	function close() {
		open = false
		memory = null
		confirmDelete = false
		error = null
		saveError = null
		deleteError = null
		onClose?.()
	}

	function renderDebugText(text: string): string {
		return text
			.replace(/\r\n/g, '⏎\r\n')
			.replace(/\n/g, '⏎\n')
			.replace(/\r/g, '↵\r')
			.replace(/\t/g, '→\t')
	}

	async function saveMemory() {
		if (!memory) return
		isSaving = true
		saveError = null
		try {
			const tags = editTags
				.split(',')
				.map((t) => t.trim())
				.filter(Boolean)
			const confidence = editConfidence.trim() !== '' ? Number(editConfidence) / 100 : null
			if (
				confidence !== null &&
				(Number.isNaN(confidence) || confidence < 0 || confidence > 1)
			) {
				throw new Error('confidence must be 0-100')
			}
			const body: MemoryUpdate = {
				content: editContent,
				tags: tags.length > 0 ? tags : null,
				confidence,
			}
			const updated = unwrap(
				await api.PUT('/v1/memories/{memory_id}', {
					params: { path: { memory_id: memory.id } },
					body,
				})
			)
			memory = updated
			editContent = updated.content
			editTags = originalTags(updated)
			editConfidence = originalConfidence(updated)
			onUpdated?.(updated)
		} catch (e: unknown) {
			saveError = e instanceof Error ? e.message : 'failed to save'
		} finally {
			isSaving = false
		}
	}

	async function deleteMemory() {
		if (!memory) return
		isDeleting = true
		deleteError = null
		try {
			await api.DELETE('/v1/memories/{memory_id}', {
				params: { path: { memory_id: memory.id } },
			})
			onDeleted?.(memory.id)
			close()
		} catch (e: unknown) {
			deleteError = e instanceof Error ? e.message : 'failed to delete'
		} finally {
			isDeleting = false
		}
	}

	$effect(() => {
		if (!browser) return
		if (!open) return
		if (!memoryId) return

		isLoading = true
		error = null
		memory = null

		api.GET('/v1/memories/{memory_id}', { params: { path: { memory_id: memoryId } } })
			.then((r) => unwrap(r))
			.then((m) => {
				memory = m
				editContent = m.content
				editTags = originalTags(m)
				editConfidence = originalConfidence(m)
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : String(e)
			})
			.finally(() => {
				isLoading = false
			})
	})
</script>

<Dialog.Root
	bind:open
	onOpenChange={(value) => {
		if (!value) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-[min(700px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="text-base font-semibold">memory details</Dialog.Title>
					<Dialog.Description class="text-xs text-zinc-500"
						>{memoryId ?? ''}</Dialog.Description
					>
				</div>
				<div class="flex shrink-0 items-center gap-1">
					{#if memory}
						{#if isDirty}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
								disabled={isSaving}
								onclick={saveMemory}
							>
								<Save class="mr-1 h-3.5 w-3.5" />
								{isSaving ? 'saving...' : 'save'}
							</Button>
						{/if}
						{#if !confirmDelete}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:bg-red-900/20 hover:text-red-300"
								onclick={() => (confirmDelete = true)}
							>
								<Trash2 class="mr-1 h-3.5 w-3.5" />
								delete
							</Button>
						{:else}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-300 hover:bg-red-900/30"
								disabled={isDeleting}
								onclick={deleteMemory}
							>
								{isDeleting ? 'deleting...' : 'confirm delete'}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400"
								onclick={() => (confirmDelete = false)}
							>
								cancel
							</Button>
						{/if}
					{/if}
					<button
						class="ml-1 rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
						onclick={close}
					>
						<X class="h-4 w-4" />
					</button>
				</div>
			</div>

			<div class="min-h-0 flex-1 overflow-y-auto p-6">
				{#if isLoading}
					<div class="flex items-center justify-center py-12">
						<NokodoLoader />
					</div>
				{:else if error}
					<div
						class="rounded-xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
					>
						{error}
					</div>
				{:else if memory}
					{#if saveError}
						<div
							class="mb-4 rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
						>
							{saveError}
						</div>
					{/if}
					{#if deleteError}
						<div
							class="mb-4 rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
						>
							{deleteError}
						</div>
					{/if}

					<div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
						<div class="space-y-3 lg:col-span-1">
							<div
								class="rounded-xl border border-zinc-800 bg-zinc-900 p-3 text-xs text-zinc-400"
							>
								<div class="space-y-1">
									<div>id: {memory.id}</div>
									<div>user: {memory.user_id}</div>
									{#if memory.source_message_id}
										<div>source: {memory.source_message_id}</div>
									{/if}
									<div>
										created: {new Date(memory.created_at).toLocaleString()}
									</div>
									<div>
										updated: {new Date(memory.updated_at).toLocaleString()}
									</div>
									{#if memory.last_accessed_at}
										<div>
											last accessed: {new Date(
												memory.last_accessed_at
											).toLocaleString()}
										</div>
									{/if}
								</div>
							</div>

							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">tags (comma-separated)</Label>
								<Input
									bind:value={editTags}
									placeholder="tag1, tag2"
									class="text-sm"
								/>
							</div>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">confidence (0–100)</Label>
								<Input
									bind:value={editConfidence}
									placeholder="e.g. 85"
									type="number"
									min="0"
									max="100"
									step="0.1"
									class="text-sm"
								/>
							</div>

							{#if memory.metadata_ && Object.keys(memory.metadata_).length > 0}
								<div class="rounded-xl border border-zinc-800 bg-zinc-900 p-3">
									<div class="mb-2 text-sm font-medium">metadata</div>
									<pre
										class="max-h-40 overflow-auto font-mono text-xs text-zinc-400">{JSON.stringify(
											memory.metadata_,
											null,
											2
										)}</pre>
								</div>
							{/if}
						</div>

						<div class="lg:col-span-2">
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">content</Label>
								<Textarea
									bind:value={editContent}
									rows={12}
									class="resize-y font-mono text-sm"
								/>
							</div>
						</div>
					</div>
				{:else}
					<div
						class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
					>
						no memory selected
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
