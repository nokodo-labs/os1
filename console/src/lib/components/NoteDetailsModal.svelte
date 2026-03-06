<script lang="ts">
	import { api, unwrap, type Schemas } from '$lib/api'

	type Note = Schemas['Note']

	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Textarea } from '$lib/components/ui/textarea'
	import {
		Calendar,
		Clock,
		FileText,
		Hash,
		Pencil,
		Save,
		Tag,
		Trash2,
		User,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		note: Note | null
		onViewUser?: (userId: string) => void
		onUpdated?: (note: Note) => void
		onDeleted?: (noteId: string) => void
	}

	let { open = $bindable(false), note, onViewUser, onUpdated, onDeleted }: Props = $props()

	let isEditing = $state(false)
	let editTitle = $state('')
	let editContent = $state('')
	let editLabels = $state('')
	let isSaving = $state(false)
	let saveError = $state<string | null>(null)
	let isDeleting = $state(false)
	let deleteError = $state<string | null>(null)
	let confirmDelete = $state(false)

	function close() {
		open = false
		isEditing = false
		confirmDelete = false
		saveError = null
		deleteError = null
	}

	function startEdit() {
		if (!note) return
		editTitle = note.title
		editContent = note.content ?? ''
		editLabels = (note.labels ?? []).join(', ')
		isEditing = true
		saveError = null
	}

	function cancelEdit() {
		isEditing = false
		saveError = null
	}

	async function saveNote() {
		if (!note) return
		isSaving = true
		saveError = null
		try {
			const r = await api.PUT('/v1/notes/{note_id}', {
				params: { path: { note_id: note.id } },
				body: {
					title: editTitle.trim(),
					content: editContent.trim() || null,
					labels: editLabels
						.split(',')
						.map((l) => l.trim())
						.filter(Boolean),
				},
			})
			const updated = unwrap(r)
			isEditing = false
			onUpdated?.(updated)
		} catch (e) {
			saveError = e instanceof Error ? e.message : 'failed to save'
		} finally {
			isSaving = false
		}
	}

	async function deleteNote() {
		if (!note) return
		isDeleting = true
		deleteError = null
		try {
			const r = await api.DELETE('/v1/notes/{note_id}', {
				params: { path: { note_id: note.id } },
			})
			unwrap(r)
			onDeleted?.(note.id)
			close()
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to delete'
		} finally {
			isDeleting = false
		}
	}
</script>

<Dialog.Root
	bind:open
	onOpenChange={(v) => {
		if (!v) close()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[85vh] w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div class="min-w-0 flex-1">
					<Dialog.Title class="truncate text-base font-semibold">
						{note?.title ?? 'note'}
					</Dialog.Title>
					<Dialog.Description class="text-xs text-zinc-500"
						>note details</Dialog.Description
					>
				</div>
				<div class="flex shrink-0 items-center gap-1">
					{#if note && !isEditing}
						<Button
							variant="ghost"
							size="sm"
							class="h-7 rounded-lg px-2 text-xs text-zinc-400 hover:text-zinc-200"
							onclick={startEdit}
						>
							<Pencil class="mr-1 h-3 w-3" />
							edit
						</Button>
						{#if !confirmDelete}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={() => (confirmDelete = true)}
							>
								<Trash2 class="mr-1 h-3 w-3" />
								delete
							</Button>
						{:else}
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-red-400 hover:text-red-300"
								onclick={deleteNote}
								disabled={isDeleting}
							>
								{isDeleting ? 'deleting…' : 'confirm?'}
							</Button>
							<Button
								variant="ghost"
								size="sm"
								class="h-7 rounded-lg px-2 text-xs text-zinc-400"
								onclick={() => (confirmDelete = false)}>cancel</Button
							>
						{/if}
					{/if}
					<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
						<X class="h-4 w-4" />
					</Button>
				</div>
			</div>

			{#if note}
				<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
					{#if deleteError}
						<div
							class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
						>
							{deleteError}
						</div>
					{/if}

					<!-- metadata -->
					<div class="space-y-1.5">
						<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
							identity
						</p>
						<div
							class="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900"
						>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Hash class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-16 shrink-0 text-xs text-zinc-500">id</span>
								<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
									>{note.id}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<User class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-16 shrink-0 text-xs text-zinc-500">user</span>
								{#if onViewUser}
									<button
										type="button"
										class="min-w-0 truncate font-mono text-xs text-zinc-300 underline underline-offset-4 hover:text-zinc-100"
										onclick={() => onViewUser?.(note.user_id)}
										>{note.user_id}</button
									>
								{:else}
									<span class="min-w-0 truncate font-mono text-xs text-zinc-300"
										>{note.user_id}</span
									>
								{/if}
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Calendar class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-16 shrink-0 text-xs text-zinc-500">created</span>
								<span class="text-xs text-zinc-300"
									>{new Date(note.created_at).toLocaleString()}</span
								>
							</div>
							<div class="flex items-center gap-3 px-4 py-2.5">
								<Clock class="h-3.5 w-3.5 shrink-0 text-zinc-500" />
								<span class="w-16 shrink-0 text-xs text-zinc-500">updated</span>
								<span class="text-xs text-zinc-300"
									>{new Date(note.updated_at).toLocaleString()}</span
								>
							</div>
							{#if note.deleted_at}
								<div class="flex items-center gap-3 px-4 py-2.5">
									<Trash2 class="h-3.5 w-3.5 shrink-0 text-red-400" />
									<span class="w-16 shrink-0 text-xs text-zinc-500">deleted</span>
									<span class="text-xs text-red-400"
										>{new Date(note.deleted_at).toLocaleString()}</span
									>
								</div>
							{/if}
						</div>
					</div>

					<!-- edit form or read view -->
					{#if isEditing}
						<div class="space-y-3">
							<p class="text-xs font-medium tracking-wider text-zinc-500 uppercase">
								edit
							</p>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">title</Label>
								<Input
									bind:value={editTitle}
									placeholder="title"
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
							</div>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">content</Label>
								<Textarea
									bind:value={editContent}
									placeholder="content"
									rows={6}
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
							</div>
							<div class="space-y-1.5">
								<Label class="text-xs text-zinc-400">labels (comma-separated)</Label
								>
								<Input
									bind:value={editLabels}
									placeholder="label1, label2"
									class="rounded-xl border-zinc-700 bg-zinc-900 text-sm text-zinc-100 placeholder-zinc-600"
								/>
							</div>
							{#if saveError}
								<div
									class="rounded-lg border border-red-900/50 bg-red-900/10 px-3 py-2 text-xs text-red-300"
								>
									{saveError}
								</div>
							{/if}
							<div class="flex gap-2">
								<Button
									variant="outline"
									size="sm"
									class="rounded-xl"
									onclick={saveNote}
									disabled={isSaving}
								>
									<Save class="mr-1.5 h-3.5 w-3.5" />
									{isSaving ? 'saving…' : 'save'}
								</Button>
								<Button
									variant="ghost"
									size="sm"
									class="rounded-xl"
									onclick={cancelEdit}>cancel</Button
								>
							</div>
						</div>
					{:else}
						<!-- labels -->
						{#if (note.labels ?? []).length > 0}
							<div class="space-y-2">
								<div
									class="flex items-center gap-2 text-xs font-medium text-zinc-500"
								>
									<Tag class="h-3.5 w-3.5" />
									labels
								</div>
								<div class="flex flex-wrap gap-1.5">
									{#each note.labels ?? [] as label (label)}
										<span
											class="rounded-lg bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300"
											>{label}</span
										>
									{/each}
								</div>
							</div>
						{/if}

						<!-- content -->
						<div class="space-y-2">
							<div class="flex items-center gap-2 text-xs font-medium text-zinc-500">
								<FileText class="h-3.5 w-3.5" />
								content
							</div>
							{#if note.content}
								<div
									class="max-h-64 overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-sm whitespace-pre-wrap text-zinc-300"
								>
									{note.content}
								</div>
							{:else}
								<div
									class="rounded-xl border border-dashed border-zinc-800 p-4 text-center text-sm text-zinc-500"
								>
									no content
								</div>
							{/if}
						</div>

						<!-- metadata_ -->
						{#if note.metadata_ && Object.keys(note.metadata_).length > 0}
							<div class="space-y-2">
								<div
									class="flex items-center gap-2 text-xs font-medium text-zinc-500"
								>
									<Clock class="h-3.5 w-3.5" />
									metadata
								</div>
								<pre
									class="max-h-48 overflow-auto rounded-xl border border-zinc-800 bg-zinc-900 p-4 text-xs text-zinc-300">{JSON.stringify(
										note.metadata_,
										null,
										2
									)}</pre>
							</div>
						{/if}
					{/if}
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
