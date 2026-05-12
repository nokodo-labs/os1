<script lang="ts">
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import { api } from '$lib/api/client'
	import type { components } from '$lib/api/types'
	import ArrowUpTray from '$lib/components/icons/ArrowUpTray.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import ModalListLayout from '$lib/components/modals/ModalListLayout.svelte'
	import { chat } from '$lib/stores/chat.svelte'
	import { session } from '$lib/stores/session.svelte'
	import { debounce } from '$lib/utils'
	import { metadataLine } from '$lib/utils/resourceAuthors'

	type Thread = components['schemas']['Thread']

	interface ArchivedChatsModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: ArchivedChatsModalProps = $props()

	const PAGE_SIZE = 20

	const sortOptions = [
		{ label: 'latest activity', value: 'last_activity_at-desc' },
		{ label: 'oldest activity', value: 'last_activity_at-asc' },
		{ label: 'newest created', value: 'created_at-desc' },
		{ label: 'oldest created', value: 'created_at-asc' },
		{ label: 'title a-z', value: 'title-asc' },
		{ label: 'title z-a', value: 'title-desc' },
	] as const

	const sortParsed: {
		sort_by: 'last_activity_at' | 'created_at' | 'title'
		sort_dir: 'asc' | 'desc'
	}[] = [
		{ sort_by: 'last_activity_at', sort_dir: 'desc' },
		{ sort_by: 'last_activity_at', sort_dir: 'asc' },
		{ sort_by: 'created_at', sort_dir: 'desc' },
		{ sort_by: 'created_at', sort_dir: 'asc' },
		{ sort_by: 'title', sort_dir: 'asc' },
		{ sort_by: 'title', sort_dir: 'desc' },
	]

	let threads = $state<Thread[]>([])
	let loading = $state(false)
	let loadingMore = $state(false)
	let search = $state('')
	let sortIndex = $state(0)
	let hasMore = $state(true)
	let unarchivingId = $state<string | null>(null)

	const currentSort = $derived(sortParsed[sortIndex])

	// client-side search filter (backend list_threads has no search param)
	const filteredThreads = $derived.by(() => {
		if (!search) return threads
		const q = search.toLowerCase()
		return threads.filter((t) => t.title?.toLowerCase().includes(q))
	})

	async function fetchThreads(opts: { reset?: boolean } = {}): Promise<void> {
		const userId = session.currentUser?.id
		if (!userId) return

		const isReset = opts.reset ?? false
		if (isReset) {
			loading = true
		} else {
			loadingMore = true
		}

		try {
			const skip = isReset ? 0 : threads.length
			const { data } = await api.GET('/v1/threads', {
				params: {
					query: {
						owner_id: userId,
						is_archived: true,
						skip,
						limit: PAGE_SIZE,
						sort_by: currentSort.sort_by,
						sort_dir: currentSort.sort_dir,
					},
				},
			})
			if (data) {
				const items = data as Thread[]
				if (isReset) {
					threads = items
				} else {
					threads = [...threads, ...items]
				}
				hasMore = items.length >= PAGE_SIZE
			}
		} finally {
			loading = false
			loadingMore = false
		}
	}

	function reload(): void {
		void fetchThreads({ reset: true })
	}

	const debouncedSearch = debounce(() => {}, 400)

	function onSearchInput(value: string): void {
		search = value
		// client-side filter; debounce just to avoid churn
		debouncedSearch()
	}

	function onSortChange(index: number): void {
		sortIndex = index
		reload()
	}

	// load on open
	$effect(() => {
		if (open) {
			threads = []
			hasMore = true
			search = ''
			sortIndex = 0
			unarchivingId = null
			reload()
		}
	})

	async function unarchiveThread(threadId: string): Promise<void> {
		unarchivingId = threadId
		try {
			const { error } = await api.PATCH('/v1/threads/{thread_id}', {
				params: { path: { thread_id: threadId } },
				body: { is_archived: false },
			})
			if (error) {
				console.error('failed to unarchive thread', error)
				return
			}
			threads = threads.filter((t) => t.id !== threadId)
			// refresh sidebar so unarchived thread appears
			void chat.refreshThreads()
		} finally {
			unarchivingId = null
		}
	}

	function openThread(threadId: string): void {
		onClose()
		void goto(resolve(`/c/${threadId}`))
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

	function archivedThreadMeta(thread: Thread): string {
		const tags = thread.tags ?? []
		const visibleTags = tags.slice(0, 3)
		const moreTags = tags.length > 3 ? `+${tags.length - 3}` : null
		return metadataLine(`created ${formatDate(thread.created_at)}`, ...visibleTags, moreTags)
	}
</script>

<BaseModal
	{open}
	title="archived chats"
	description="browse and restore archived threads"
	{onClose}
	widthClassName="max-w-3xl"
>
	<ModalListLayout
		{search}
		searchPlaceholder="search archived chats..."
		{sortOptions}
		{sortIndex}
		{loading}
		{loadingMore}
		{hasMore}
		isEmpty={filteredThreads.length === 0}
		emptyMessage="no archived chats"
		emptySearchMessage="no archived chats match your search."
		{onSearchInput}
		{onSortChange}
		onLoadMore={() => void fetchThreads()}
	>
		{#snippet items()}
			{#each filteredThreads as thread (thread.id)}
				<div
					class="group rounded-container border-foreground/8 bg-foreground/3 hover:bg-foreground/5 flex items-center gap-3 border px-5 py-2.5 transition-colors"
				>
					<button
						type="button"
						class="min-w-0 flex-1 cursor-pointer text-left"
						onclick={() => openThread(thread.id)}
					>
						<!-- primary row: title + timestamp -->
						<div class="flex items-center gap-2">
							<span
								class="min-w-0 flex-1 overflow-hidden text-sm leading-normal font-medium text-ellipsis whitespace-nowrap {thread.title
									? 'text-foreground/85'
									: 'text-foreground/40 italic'}"
							>
								{thread.title || 'untitled'}
							</span>
							<span class="text-foreground/35 ml-auto shrink-0 text-[11px]">
								{formatDate(thread.last_activity_at)}
							</span>
						</div>
						<div class="text-foreground/35 mt-0.5 truncate text-[11px]">
							{archivedThreadMeta(thread)}
						</div>
					</button>
					<button
						type="button"
						class="rounded-circle text-foreground/40 hover:bg-foreground/10 hover:text-foreground/70 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center transition-colors disabled:opacity-40"
						disabled={unarchivingId === thread.id}
						onclick={() => void unarchiveThread(thread.id)}
						aria-label="unarchive thread"
						title="unarchive"
					>
						{#if unarchivingId === thread.id}
							<div
								class="border-foreground/20 h-4 w-4 animate-spin rounded-full border-2 border-t-white/60"
							></div>
						{:else}
							<ArrowUpTray class="h-4 w-4" />
						{/if}
					</button>
				</div>
			{/each}
		{/snippet}

		{#snippet footerLeft()}
			{filteredThreads.length}
			{filteredThreads.length === 1 ? 'thread' : 'threads'}
		{/snippet}

		{#snippet footerRight()}
			<!-- close handled by BaseModal X button -->
		{/snippet}
	</ModalListLayout>
</BaseModal>
