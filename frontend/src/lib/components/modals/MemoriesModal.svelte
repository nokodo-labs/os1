<script lang="ts">
	import { apiClient } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import Check from '$lib/components/icons/Check.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce } from '$lib/utils'

	type MemorySchema = components['schemas']['Memory']

	interface MemoriesModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: MemoriesModalProps = $props()

	const PAGE_SIZE = 20

	type SortField =
		| 'updated_at'
		| 'created_at'
		| 'content_length'
		| 'category'
		| 'last_accessed_at'
		| 'confidence'

	type SortOption = {
		label: string
		sort_by: SortField
		sort_dir: 'asc' | 'desc'
	}

	const sortOptions: SortOption[] = [
		{ label: 'latest updated', sort_by: 'updated_at', sort_dir: 'desc' },
		{ label: 'oldest updated', sort_by: 'updated_at', sort_dir: 'asc' },
		{ label: 'latest created', sort_by: 'created_at', sort_dir: 'desc' },
		{ label: 'oldest created', sort_by: 'created_at', sort_dir: 'asc' },
		{ label: 'longest', sort_by: 'content_length', sort_dir: 'desc' },
		{ label: 'shortest', sort_by: 'content_length', sort_dir: 'asc' },
	]

	let memories = $state<MemorySchema[]>([])
	let loading = $state(false)
	let loadingMore = $state(false)
	let search = $state('')
	let sortIndex = $state(0)
	let editingId = $state<string | null>(null)
	let editContent = $state('')
	let deletingAll = $state(false)
	let scrollContainer = $state<HTMLDivElement | null>(null)
	let hasMore = $state(true)

	const currentSort = $derived(sortOptions[sortIndex])

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
			const skip = isReset ? 0 : memories.length
			const { data } = await apiClient().GET('/v1/memories', {
				params: {
					query: {
						user_id: userId,
						skip,
						limit: PAGE_SIZE,
						sort_by: currentSort.sort_by,
						sort_dir: currentSort.sort_dir,
						search: search || undefined,
					},
				},
			})
			if (data) {
				const items = data as unknown as MemorySchema[]
				if (isReset) {
					memories = items
				} else {
					memories = [...memories, ...items]
				}
				hasMore = items.length >= PAGE_SIZE
			}
		} finally {
			loading = false
			loadingMore = false
		}
	}

	function reload(): void {
		void fetchMemories({ reset: true })
	}

	const debouncedSearch = debounce(() => reload(), 400)

	function onSearchInput(value: string): void {
		search = value
		debouncedSearch()
	}

	function onSortChange(index: number): void {
		sortIndex = index
		reload()
	}

	// load on open
	$effect(() => {
		if (open) {
			memories = []
			hasMore = true
			search = ''
			sortIndex = 0
			editingId = null
			reload()
		}
	})

	// infinite scroll
	function onScroll(e: Event): void {
		const el = e.currentTarget as HTMLDivElement
		if (!el || loadingMore || !hasMore) return
		const threshold = 100
		if (el.scrollHeight - el.scrollTop - el.clientHeight < threshold) {
			void fetchMemories()
		}
	}

	// edit
	function startEdit(memory: MemorySchema): void {
		editingId = memory.id
		editContent = memory.content
	}

	function cancelEdit(): void {
		editingId = null
		editContent = ''
	}

	async function saveEdit(memoryId: string): Promise<void> {
		const trimmed = editContent.trim()
		if (!trimmed) return
		await apiClient().PUT('/v1/memories/{memory_id}', {
			params: { path: { memory_id: memoryId } },
			body: { content: trimmed },
		})
		const idx = memories.findIndex((m) => m.id === memoryId)
		if (idx >= 0) {
			memories[idx] = { ...memories[idx], content: trimmed }
		}
		editingId = null
		editContent = ''
	}

	// delete single
	async function deleteMemory(memoryId: string): Promise<void> {
		await apiClient().DELETE('/v1/memories/{memory_id}', {
			params: { path: { memory_id: memoryId } },
		})
		memories = memories.filter((m) => m.id !== memoryId)
	}

	// delete all
	async function deleteAll(): Promise<void> {
		deletingAll = true
		try {
			await apiClient().DELETE('/v1/memories', {})
			memories = []
			hasMore = false
		} finally {
			deletingAll = false
		}
	}

	function formatDate(dateStr: string): string {
		const d = new Date(dateStr)
		const now = new Date()
		const diffMs = now.getTime() - d.getTime()
		const diffDays = Math.floor(diffMs / 86400000)
		if (diffDays === 0) return 'today'
		if (diffDays === 1) return 'yesterday'
		if (diffDays < 7) return `${diffDays}d ago`
		if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
		return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
	}
</script>

<BaseModal
	{open}
	title="memories"
	description="manage what the AI remembers about you"
	{onClose}
	widthClassName="max-w-2xl"
>
	<div class="flex flex-col gap-3">
		<!-- toolbar: search + sort + delete all -->
		<div class="flex items-center gap-2">
			<div class="relative flex-1">
				<Search
					class="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-white/40"
				/>
				<input
					type="text"
					class="rounded-pill w-full border border-white/10 bg-white/5 py-2 pr-3 pl-9 text-sm text-white/90 placeholder-white/30 transition-colors outline-none focus:border-white/20 focus:bg-white/8"
					placeholder="search memories..."
					value={search}
					oninput={(e) => onSearchInput(e.currentTarget.value)}
				/>
			</div>
			<select
				class="rounded-pill border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70 transition-colors outline-none focus:border-white/20 [&>option]:bg-neutral-900 [&>option]:text-white/90"
				value={sortIndex}
				onchange={(e) => onSortChange(Number(e.currentTarget.value))}
			>
				{#each sortOptions as opt, i (opt.sort_by + opt.sort_dir)}
					<option value={i}>{opt.label}</option>
				{/each}
			</select>
		</div>

		<!-- memories list -->
		<div
			bind:this={scrollContainer}
			class="max-h-80 min-h-40 overflow-y-auto"
			onscroll={onScroll}
		>
			{#if loading}
				<div class="flex items-center justify-center py-12">
					<div
						class="h-5 w-5 animate-spin rounded-full border-2 border-white/20 border-t-white/60"
					></div>
				</div>
			{:else if memories.length === 0}
				<div class="rounded-xl border border-white/8 bg-white/3 p-6">
					<p class="text-center text-sm text-white/40">
						{search
							? 'no memories match your search.'
							: 'no memories yet. the AI will remember things as you chat.'}
					</p>
				</div>
			{:else}
				<div class="space-y-2">
					{#each memories as memory (memory.id)}
						<div
							class="group rounded-xl border border-white/8 bg-white/3 px-4 py-3 transition-colors hover:bg-white/5"
						>
							{#if editingId === memory.id}
								<!-- editing mode -->
								<textarea
									class="w-full resize-none rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white/90 outline-none focus:border-white/25"
									rows="3"
									bind:value={editContent}
								></textarea>
								<div class="mt-2 flex items-center justify-end gap-1.5">
									<button
										type="button"
										class="rounded-pill flex items-center gap-1 border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/60 transition-colors hover:bg-white/10 hover:text-white/80"
										onclick={cancelEdit}
									>
										<XMark class="h-3.5 w-3.5" />
										cancel
									</button>
									<button
										type="button"
										class="rounded-pill flex items-center gap-1 border border-white/10 bg-white/10 px-2.5 py-1 text-xs text-white/80 transition-colors hover:bg-white/15"
										onclick={() => void saveEdit(memory.id)}
									>
										<Check class="h-3.5 w-3.5" />
										save
									</button>
								</div>
							{:else}
								<!-- display mode -->
								<div class="flex items-start justify-between gap-3">
									<div class="min-w-0 flex-1">
										<p class="text-sm leading-relaxed text-white/80">
											{memory.content}
										</p>
										<p class="mt-1.5 text-xs text-white/35">
											{formatDate(memory.updated_at)}
										</p>
									</div>
									<div
										class="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100"
									>
										<button
											type="button"
											class="flex h-7 w-7 items-center justify-center rounded-lg text-white/40 transition-colors hover:bg-white/10 hover:text-white/70"
											onclick={() => startEdit(memory)}
											aria-label="edit memory"
										>
											<Pencil class="h-3.5 w-3.5" />
										</button>
										<button
											type="button"
											class="flex h-7 w-7 items-center justify-center rounded-lg text-white/40 transition-colors hover:bg-red-500/15 hover:text-red-400"
											onclick={() => void deleteMemory(memory.id)}
											aria-label="delete memory"
										>
											<Trash class="h-3.5 w-3.5" />
										</button>
									</div>
								</div>
							{/if}
						</div>
					{/each}

					{#if loadingMore}
						<div class="flex items-center justify-center py-3">
							<div
								class="h-4 w-4 animate-spin rounded-full border-2 border-white/20 border-t-white/60"
							></div>
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- footer: count + delete all -->
		<div class="flex items-center justify-between border-t border-white/10 pt-3">
			<span class="text-xs text-white/40">
				{memories.length}
				{memories.length === 1 ? 'memory' : 'memories'}
			</span>
			<div class="flex items-center gap-2">
				{#if memories.length > 0}
					<button
						type="button"
						class="rounded-pill flex items-center gap-1.5 border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs text-red-400 transition-colors hover:border-red-500/50 hover:bg-red-500/20 disabled:opacity-50"
						disabled={deletingAll}
						onclick={() => void deleteAll()}
					>
						<Trash class="h-3.5 w-3.5" />
						{deletingAll ? 'deleting...' : 'delete all'}
					</button>
				{/if}
				<button
					type="button"
					class="rounded-pill border border-white/10 bg-white/10 px-4 py-1.5 text-xs font-semibold text-white/85 transition-colors hover:bg-white/15"
					onclick={onClose}
				>
					close
				</button>
			</div>
		</div>
	</div>
</BaseModal>
