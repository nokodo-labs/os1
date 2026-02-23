<script lang="ts">
	import type { Schemas } from '$lib/api'

	type Note = Schemas['Note']

	import { Button } from '$lib/components/ui/button'
	import { Calendar, Clock, FileText, Hash, Pencil, Tag, Trash2, User, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'

	type Props = {
		open: boolean
		note: Note | null
		onViewUser?: (userId: string) => void
	}

	let { open = $bindable(false), note, onViewUser }: Props = $props()

	function close() {
		open = false
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
					<Dialog.Title class="truncate text-lg font-semibold">
						{note?.title ?? 'note'}
					</Dialog.Title>
					<Dialog.Description class="text-sm text-zinc-400"
						>note details</Dialog.Description
					>
				</div>
				<Button variant="ghost" size="icon" class="shrink-0 rounded-xl" onclick={close}>
					<X class="h-4 w-4" />
				</Button>
			</div>

			{#if note}
				<div class="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-4">
					<!-- metadata grid -->
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div class="flex items-center gap-2 text-zinc-400">
							<Hash class="h-3.5 w-3.5 shrink-0" />
							<span class="truncate">{note.id}</span>
						</div>
						<div class="flex items-center gap-2 text-zinc-400">
							<User class="h-3.5 w-3.5 shrink-0" />
							{#if onViewUser}
								<button
									type="button"
									class="truncate underline underline-offset-4 hover:text-zinc-200"
									onclick={() => onViewUser?.(note.user_id)}
								>
									{note.user_id}
								</button>
							{:else}
								<span class="truncate">{note.user_id}</span>
							{/if}
						</div>
						<div class="flex items-center gap-2 text-zinc-400">
							<Calendar class="h-3.5 w-3.5 shrink-0" />
							<span>created {new Date(note.created_at).toLocaleString()}</span>
						</div>
						<div class="flex items-center gap-2 text-zinc-400">
							<Pencil class="h-3.5 w-3.5 shrink-0" />
							<span>updated {new Date(note.updated_at).toLocaleString()}</span>
						</div>
						{#if note.deleted_at}
							<div class="col-span-2 flex items-center gap-2 text-red-400">
								<Trash2 class="h-3.5 w-3.5 shrink-0" />
								<span>deleted {new Date(note.deleted_at).toLocaleString()}</span>
							</div>
						{/if}
					</div>

					<!-- labels -->
					{#if (note.labels ?? []).length > 0}
						<div class="space-y-2">
							<div class="flex items-center gap-2 text-sm font-medium text-zinc-300">
								<Tag class="h-3.5 w-3.5" />
								labels
							</div>
							<div class="flex flex-wrap gap-1.5">
								{#each note.labels ?? [] as label (label)}
									<span
										class="rounded-lg bg-zinc-800 px-2.5 py-1 text-xs text-zinc-300"
									>
										{label}
									</span>
								{/each}
							</div>
						</div>
					{/if}

					<!-- content -->
					<div class="space-y-2">
						<div class="flex items-center gap-2 text-sm font-medium text-zinc-300">
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

					<!-- metadata -->
					{#if note.metadata_ && Object.keys(note.metadata_).length > 0}
						<div class="space-y-2">
							<div class="flex items-center gap-2 text-sm font-medium text-zinc-300">
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
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
