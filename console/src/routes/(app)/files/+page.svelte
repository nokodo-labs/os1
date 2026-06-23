<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type File = Schemas['File']
	type SortDir = 'asc' | 'desc'

	import FileDetailsModal from '$lib/components/FileDetailsModal.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		ChevronLeft,
		ChevronRight,
		FileIcon,
		RefreshCw,
		Trash2,
	} from '@lucide/svelte'

	type SortKey = 'created_at' | 'updated_at' | 'filename' | 'size_bytes'

	const sortOrder: SortKey[] = ['created_at', 'updated_at', 'filename', 'size_bytes']

	function sortLabel(key: SortKey): string {
		switch (key) {
			case 'created_at':
				return 'created at'
			case 'updated_at':
				return 'updated at'
			case 'filename':
				return 'filename'
			case 'size_bytes':
				return 'size'
		}
	}

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'filename') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'created_at'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let pageIndex = $state(0)
	let limit = $state(20)
	let refreshToken = $state(0)

	let files = $state<File[]>([])
	let isLoading = $state(false)
	let error = $state<string | null>(null)
	let hasNext = $state(false)
	let total = $state(0)
	let ownerIdFilter = $state<string | null>(null)

	let deletingId = $state<string | null>(null)
	let deleteError = $state<string | null>(null)
	let confirmDeleteId = $state<string | null>(null)

	let selectedFile = $state<File | null>(null)
	let detailOpen = $state(false)

	function openDetail(file: File) {
		selectedFile = file
		detailOpen = true
	}

	function handleDeleteFromModal(fileId: string) {
		files = files.filter((f) => f.id !== fileId)
	}

	function handleUpdateFromModal(file: File) {
		files = files.map((current) => (current.id === file.id ? file : current))
		selectedFile = file
	}

	$effect(() => {
		if (!browser) return

		const user = page.url.searchParams.get('user')
		const nextOwner = user?.trim() || null

		if (ownerIdFilter !== nextOwner) pageIndex = 0
		ownerIdFilter = nextOwner
	})

	$effect(() => {
		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null

		Promise.all([
			api
				.GET('/v1/files', {
					params: {
						query: {
							skip,
							limit,
							include_deleted: true,
							sort_by: sortKey,
							sort_dir: sortDir,
							...(ownerIdFilter ? { owner_id: ownerIdFilter } : {}),
						},
					},
				})
				.then((r) => unwrap(r)),
			api
				.GET('/v1/files/count', {
					params: {
						query: {
							include_deleted: true,
							...(ownerIdFilter ? { owner_id: ownerIdFilter } : {}),
						},
					},
				})
				.then((r) => unwrap(r)),
		])
			.then(([result, count]) => {
				files = result
				total = count.total
				hasNext = (pageIndex + 1) * limit < count.total
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load files'
				files = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})

	function refresh() {
		refreshToken += 1
	}

	function setSort(next: SortKey) {
		sortKey = next
		sortDir = defaultSortDir(next)
		pageIndex = 0
	}

	function toggleSortDir() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc'
		pageIndex = 0
	}

	async function deleteFile(fileId: string) {
		deletingId = fileId
		deleteError = null
		try {
			const r = await api.DELETE('/v1/files/{file_id}', {
				params: { path: { file_id: fileId } },
			})
			if (r.error) {
				const detail = r.error?.detail
				deleteError = typeof detail === 'string' ? detail : 'failed to delete file'
			} else {
				files = files.filter((f) => f.id !== fileId)
			}
		} catch (e) {
			deleteError = e instanceof Error ? e.message : 'failed to delete file'
		} finally {
			deletingId = null
			confirmDeleteId = null
		}
	}

	function formatBytes(n: number | null | undefined): string {
		if (n == null) return '—'
		if (n < 1024) return `${n} B`
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
		if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
		return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
	}

	function formatDate(s: string): string {
		return new Date(s).toLocaleString()
	}
</script>

<div class="flex flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">files</h2>
			<p class="text-zinc-400">all uploaded and registered files in the system.</p>
		</div>
		<div class="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center">
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
					<SelectTrigger class="w-full flex-1 rounded-xl sm:w-44">
						<span class="truncate text-left">{sortLabel(sortKey)}</span>
					</SelectTrigger>
					<SelectContent>
						{#each sortOrder as key (key)}
							<SelectItem value={key}>{sortLabel(key)}</SelectItem>
						{/each}
					</SelectContent>
				</Select>
				<Button
					variant="outline"
					class="shrink-0 rounded-xl px-3"
					onclick={() => toggleSortDir()}
					disabled={isLoading}
					title="toggle sort direction"
				>
					{#if sortDir === 'asc'}
						<ArrowUp class="h-4 w-4" />
					{:else}
						<ArrowDown class="h-4 w-4" />
					{/if}
				</Button>
			</div>
			<div class="flex w-full items-center gap-2 sm:w-auto">
				<Button
					variant="outline"
					class="flex-1 rounded-xl sm:flex-none"
					onclick={() => refresh()}
					disabled={isLoading}
				>
					<RefreshCw class="mr-2 h-4 w-4 {isLoading ? 'animate-spin' : ''}" />
					{isLoading ? 'loading...' : 'refresh'}
				</Button>
			</div>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
		</div>
	{/if}

	{#if deleteError}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{deleteError}
		</div>
	{/if}

	<div class="flex flex-col gap-4">
		<div class="flex items-center justify-end">
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex = Math.max(0, pageIndex - 1)
					}}
					disabled={pageIndex === 0 || isLoading}
				>
					<ChevronLeft class="mr-1.5 h-4 w-4" />
					prev
				</Button>
				<span class="text-xs text-zinc-400 tabular-nums">
					{total > 0
						? `items ${pageIndex * limit + 1}–${pageIndex * limit + files.length} of ${total}`
						: ''}
				</span>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex += 1
					}}
					disabled={!hasNext || isLoading}
				>
					next
					<ChevronRight class="ml-1.5 h-4 w-4" />
				</Button>
			</div>
		</div>
		<div class="flex flex-col space-y-2">
			{#if isLoading && files.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if files.length === 0}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no files found
				</div>
			{:else}
				{#each files as file (file.id)}
					<div
						role="button"
						tabindex="0"
						class="flex w-full cursor-pointer items-center justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
						onclick={() => openDetail(file)}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') openDetail(file)
						}}
					>
						<div class="flex min-w-0 flex-1 items-center gap-4">
							<div
								class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-rose-500/15 text-rose-400"
							>
								<FileIcon class="h-5 w-5" />
							</div>
							<div class="min-w-0 flex-1 space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<span class="truncate text-base font-medium text-zinc-100"
										>{file.filename ?? '(no filename)'}</span
									>
								</div>
								<div
									class="flex flex-wrap items-center gap-3 text-xs text-zinc-500"
								>
									<span
										class="inline-flex items-center gap-1.5 font-mono text-[10px] opacity-50"
									>
										{file.id}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										{file.mime_type ?? 'unknown type'}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										{formatBytes(file.size_bytes)}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										{file.source}
									</span>
									<span
										class="inline-flex items-center gap-1 rounded-md bg-zinc-800 px-2 py-0.5 text-[10px] font-medium tracking-wider text-zinc-300 uppercase"
									>
										{file.status}
									</span>
								</div>
							</div>
						</div>
						<div class="flex shrink-0 flex-col items-end text-xs text-zinc-500">
							<div class="flex items-center gap-1.5 whitespace-nowrap">
								{#if file.deleted_at}
									<span class="text-red-400"
										>deleted {formatDate(file.deleted_at)}</span
									>
								{:else}
									<span>{formatDate(file.created_at)}</span>
								{/if}
							</div>
						</div>
						<div class="shrink-0" onclick={(e) => e.stopPropagation()} role="none">
							{#if confirmDeleteId === file.id}
								<div class="flex items-center gap-2">
									<span class="text-xs text-zinc-400">delete?</span>
									<Button
										variant="destructive"
										size="sm"
										class="rounded-lg"
										disabled={deletingId === file.id}
										onclick={() => deleteFile(file.id)}
									>
										{deletingId === file.id ? 'deleting…' : 'yes'}
									</Button>
									<Button
										variant="outline"
										size="sm"
										class="rounded-lg"
										onclick={() => {
											confirmDeleteId = null
										}}
									>
										no
									</Button>
								</div>
							{:else}
								<Button
									variant="ghost"
									size="sm"
									class="rounded-lg text-zinc-500 hover:text-red-400"
									disabled={!!deletingId}
									onclick={() => {
										confirmDeleteId = file.id
										deleteError = null
									}}
									title="delete file"
								>
									<Trash2 class="h-4 w-4" />
								</Button>
							{/if}
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>

<FileDetailsModal
	bind:open={detailOpen}
	file={selectedFile}
	onUpdated={handleUpdateFromModal}
	onDeleted={handleDeleteFromModal}
/>
