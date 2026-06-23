<script lang="ts">
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ModalListLayout from '$lib/components/modals/ModalListLayout.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { showError } from '$lib/stores/notifications.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce } from '$lib/utils'
	import { untrack } from 'svelte'

	type MemorySchema = components['schemas']['Memory']
	type SearchResultItem = components['schemas']['SearchResultItem']

	type DisplayMemory = {
		id: string
		content: string
		created_at: string
		updated_at: string
	}

	interface MemoriesModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: MemoriesModalProps = $props()

	const PAGE_SIZE = 100
	const SEARCH_PAGE_SIZE = 50

	const sortOptions = [
		{ label: 'latest updated', value: 'updated_at-desc' },
		{ label: 'oldest updated', value: 'updated_at-asc' },
		{ label: 'latest created', value: 'created_at-desc' },
		{ label: 'oldest created', value: 'created_at-asc' },
		{ label: 'longest', value: 'content_length-desc' },
		{ label: 'shortest', value: 'content_length-asc' },
	] as const

	type SortField =
		| 'updated_at'
		| 'created_at'
		| 'content_length'
		| 'tags'
		| 'last_accessed_at'
		| 'confidence'

	const sortParsed: { sort_by: SortField; sort_dir: 'asc' | 'desc' }[] = [
		{ sort_by: 'updated_at', sort_dir: 'desc' },
		{ sort_by: 'updated_at', sort_dir: 'asc' },
		{ sort_by: 'created_at', sort_dir: 'desc' },
		{ sort_by: 'created_at', sort_dir: 'asc' },
		{ sort_by: 'content_length', sort_dir: 'desc' },
		{ sort_by: 'content_length', sort_dir: 'asc' },
	]

	let memories = $state<DisplayMemory[]>([])
	let loading = $state(false)
	let loadingMore = $state(false)
	let search = $state('')
	let sortIndex = $state(0)
	let editingId = $state<string | null>(null)
	let editContent = $state('')
	let savingEditId = $state<string | null>(null)
	let deletingAll = $state(false)
	let hasMore = $state(true)
	let memoryTotal = $state<number | null>(null)

	const currentSort = $derived(sortParsed[sortIndex])
	const isSearching = $derived(search.trim().length > 0)

	function toDisplayMemory(item: MemorySchema | SearchResultItem): DisplayMemory {
		const content = 'content' in item ? item.content : item.title
		return {
			id: item.id,
			content,
			created_at: item.created_at,
			updated_at: item.updated_at,
		}
	}

	async function fetchMemoryTotal(): Promise<void> {
		const userId = session.currentUser?.id
		if (!userId) return
		const { data } = await api.GET('/v1/memories/count', {
			params: { query: { owner_id: userId } },
		})
		memoryTotal = typeof data === 'number' ? data : null
	}

	async function fetchListPage(userId: string, isReset: boolean): Promise<void> {
		const skip = isReset ? 0 : memories.length
		const { data } = await api.GET('/v1/memories', {
			params: {
				query: {
					owner_id: userId,
					skip,
					limit: PAGE_SIZE,
					sort_by: currentSort.sort_by,
					sort_dir: currentSort.sort_dir,
				},
			},
		})
		if (!data) return
		const items = (data as unknown as MemorySchema[]).map(toDisplayMemory)
		memories = isReset ? items : [...memories, ...items]
		hasMore = items.length >= PAGE_SIZE
	}

	async function fetchSearchPage(userId: string, query: string, isReset: boolean): Promise<void> {
		const offset = isReset ? 0 : memories.length
		const { data } = await api.GET('/v1/memories/search', {
			params: {
				query: {
					q: query,
					limit: SEARCH_PAGE_SIZE,
					offset,
					mode: 'full',
					owner_id: userId,
				},
			},
		})
		if (!data) return
		const items = data.items.map(toDisplayMemory)
		memories = isReset ? items : [...memories, ...items]
		hasMore = data.has_more
	}

	async function fetchMemories(opts: { reset?: boolean } = {}): Promise<void> {
		const userId = session.currentUser?.id
		if (!userId) return

		const isReset = opts.reset ?? false
		if (isReset) {
			loading = true
		} else {
			loadingMore = true
		}

		try {
			const query = search.trim()
			if (query) {
				await fetchSearchPage(userId, query, isReset)
			} else {
				await fetchListPage(userId, isReset)
			}
		} finally {
			loading = false
			loadingMore = false
		}
	}

	function reload(): void {
		memoryTotal = null
		void fetchMemories({ reset: true })
		if (!isSearching) void fetchMemoryTotal()
	}

	const debouncedSearch = debounce(() => reload(), 400)

	function onSearchInput(value: string): void {
		search = value
		if (value.trim() === '') {
			reload()
		} else {
			debouncedSearch()
		}
	}

	function onSortChange(index: number): void {
		sortIndex = index
		reload()
	}

	// load on open. untrack so this only reacts to `open`, never to the
	// state it resets (otherwise typing in search re-triggers the reset).
	$effect(() => {
		if (!open) return
		untrack(() => {
			memories = []
			hasMore = true
			memoryTotal = null
			search = ''
			sortIndex = 0
			editingId = null
			savingEditId = null
			reload()
		})
	})

	// edit
	function startEdit(memory: DisplayMemory): void {
		editingId = memory.id
		editContent = memory.content
	}

	function cancelEdit(): void {
		editingId = null
		editContent = ''
	}

	async function saveEdit(memoryId: string): Promise<void> {
		if (savingEditId) return
		const trimmed = editContent.trim()
		if (!trimmed) return
		savingEditId = memoryId
		try {
			const { error } = await api.PUT('/v1/memories/{memory_id}', {
				params: { path: { memory_id: memoryId } },
				body: { content: trimmed },
			})
			if (error) {
				showError('could not save memory')
				return
			}
			const idx = memories.findIndex((m) => m.id === memoryId)
			if (idx >= 0) {
				memories[idx] = { ...memories[idx], content: trimmed }
			}
			editingId = null
			editContent = ''
		} catch {
			showError('could not save memory')
		} finally {
			savingEditId = null
		}
	}

	// delete single
	async function deleteMemory(memoryId: string): Promise<boolean> {
		try {
			await api.DELETE('/v1/memories/{memory_id}', {
				params: { path: { memory_id: memoryId } },
			})
			memories = memories.filter((m) => m.id !== memoryId)
			if (memoryTotal !== null) memoryTotal = Math.max(0, memoryTotal - 1)
			return true
		} catch {
			return false
		}
	}

	function confirmDeleteSingle(memory: DisplayMemory): void {
		modals.open('confirm-delete', {
			title: 'delete memory?',
			description: memory.content,
			onDelete: () => deleteMemory(memory.id),
		})
	}

	// delete all
	async function deleteAll(): Promise<boolean> {
		deletingAll = true
		try {
			await api.DELETE('/v1/memories', {})
			memories = []
			memoryTotal = 0
			hasMore = false
			return true
		} catch {
			return false
		} finally {
			deletingAll = false
		}
	}

	function confirmDeleteAll(): void {
		modals.open('confirm-delete', {
			title: 'delete all memories?',
			description:
				memoryTotal !== null
					? `this will permanently delete all ${memoryTotal} memories`
					: 'this will permanently delete all memories',
			onDelete: deleteAll,
		})
	}

	function formatDateTime(dateStr: string): string {
		const d = new Date(dateStr)
		if (Number.isNaN(d.getTime())) return 'unknown'
		return d.toLocaleString(undefined, {
			year: 'numeric',
			month: 'numeric',
			day: 'numeric',
			hour: 'numeric',
			minute: '2-digit',
		})
	}

	function footerCountLabel(): string {
		if (isSearching) {
			const noun = memories.length === 1 ? 'result' : 'results'
			return `${memories.length} ${noun}`
		}
		const noun = memoryTotal === 1 ? 'memory' : 'memories'
		if (memoryTotal !== null) return `${memories.length} of ${memoryTotal} ${noun} loaded`
		return `${memories.length} ${memories.length === 1 ? 'memory' : 'memories'} loaded`
	}
</script>

<BaseModal
	{open}
	title="memories"
	description="manage what the AI remembers about you"
	{onClose}
	widthClassName="max-w-5xl"
>
	<ModalListLayout
		{search}
		searchPlaceholder="search memories"
		{sortOptions}
		{sortIndex}
		{loading}
		{loadingMore}
		{hasMore}
		isEmpty={memories.length === 0}
		emptyMessage="no memories yet. the AI will remember things as you chat."
		emptySearchMessage="no memories match your search."
		{onSearchInput}
		{onSortChange}
		onLoadMore={() => void fetchMemories()}
		loadMoreThreshold={1600}
	>
		{#snippet items()}
			{#each memories as memory (memory.id)}
				<div
					class="group rounded-container border-foreground/8 bg-foreground/3 hover:bg-foreground/5 border px-4 py-3 transition-colors"
				>
					{#if editingId === memory.id}
						<!-- editing mode -->
						<textarea
							class="border-foreground/15 bg-foreground/5 text-foreground/90 focus:border-foreground/25 w-full resize-none rounded-lg border px-3 py-2 text-sm outline-none"
							rows="3"
							bind:value={editContent}
						></textarea>
						<div class="mt-2 flex items-center justify-end gap-1.5">
							<button
								type="button"
								class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/60 hover:bg-foreground/10 hover:text-foreground/80 flex items-center gap-1 border px-2.5 py-1 text-xs transition-colors"
								onclick={cancelEdit}
							>
								<XMark class="h-3.5 w-3.5" />
								discard
							</button>
							<button
								type="button"
								class="rounded-pill border-foreground/10 bg-foreground/10 text-foreground/80 hover:bg-foreground/15 flex items-center gap-1 border px-2.5 py-1 text-xs transition-colors"
								disabled={savingEditId !== null}
								onclick={() => void saveEdit(memory.id)}
							>
								<Check class="h-3.5 w-3.5" />
								{#if savingEditId === memory.id}
									<ShimmerText className="inline-block">saving</ShimmerText>
								{:else}
									save
								{/if}
							</button>
						</div>
					{:else}
						<!-- display mode -->
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0 flex-1">
								<p class="text-foreground/80 text-sm leading-relaxed">
									{memory.content}
								</p>
								<p class="text-foreground/50 mt-1.5 text-xs">
									created {formatDateTime(
										memory.created_at
									)}{memory.updated_at !== memory.created_at
										? ` · updated ${formatDateTime(memory.updated_at)}`
										: ''}
								</p>
							</div>
							<div
								class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100"
							>
								<button
									type="button"
									class="rounded-circle text-foreground/40 hover:bg-foreground/10 hover:text-foreground/70 flex h-7 w-7 cursor-pointer items-center justify-center transition-colors"
									onclick={() => startEdit(memory)}
									aria-label="edit memory"
								>
									<Pencil class="h-3.5 w-3.5" />
								</button>
								<button
									type="button"
									class="rounded-circle text-foreground/40 flex h-7 w-7 cursor-pointer items-center justify-center transition-colors hover:bg-red-500/15 hover:text-red-400"
									onclick={() => confirmDeleteSingle(memory)}
									aria-label="delete memory"
								>
									<Trash class="h-3.5 w-3.5" />
								</button>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		{/snippet}

		{#snippet footerLeft()}
			{footerCountLabel()}
		{/snippet}

		{#snippet footerRight()}
			{#if memories.length > 0}
				<button
					type="button"
					class="rounded-pill flex cursor-pointer items-center gap-1.5 border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400 transition-colors hover:border-red-500/50 hover:bg-red-500/20 disabled:opacity-50"
					disabled={deletingAll}
					onclick={confirmDeleteAll}
				>
					<Trash class="h-3.5 w-3.5" />
					{#if deletingAll}<ShimmerText className="inline-block">deleting</ShimmerText
						>{:else}delete all{/if}
				</button>
			{/if}
		{/snippet}
	</ModalListLayout>
</BaseModal>
