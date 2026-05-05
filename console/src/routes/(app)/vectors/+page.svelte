<script lang="ts">
	import { api, unwrap } from '$lib/api'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Card, CardContent } from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { Database, RefreshCw, Search, Trash2, X } from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { onMount } from 'svelte'

	// -- types (will be generated from backend) --

	interface CollectionInfo {
		name: string
		points_count: number
		vectors_count: number
		status: string
	}

	interface SearchResult {
		id: string
		score: number
		content: string
		metadata: Record<string, unknown>
	}

	type RevectorizeResult = Record<string, number>

	// -- state --

	let collections = $state<CollectionInfo[]>([])
	let isFetching = $state(true)
	let error = $state<string | null>(null)

	// search state
	let showSearchModal = $state(false)
	let searchQuery = $state('')
	let searchCollection = $state<string | null>(null)
	let searchMode = $state('hybrid')
	let searchLimit = $state(10)
	let searchResults = $state<SearchResult[]>([])
	let isSearching = $state(false)
	let searchError = $state<string | null>(null)

	// reindex state
	let isReindexing = $state(false)
	let revectorizeResult = $state<RevectorizeResult | null>(null)

	// per-resource revectorize state
	type ResourceKey = 'notes' | 'threads' | 'memories' | 'reminders' | 'calendar_events'
	const RESOURCE_KEYS: ResourceKey[] = [
		'notes',
		'threads',
		'memories',
		'reminders',
		'calendar_events',
	]
	const RESOURCE_ENDPOINTS = {
		notes: '/v1/notes/revectorize',
		threads: '/v1/threads/revectorize',
		memories: '/v1/memories/revectorize',
		reminders: '/v1/reminders/revectorize',
		calendar_events: '/v1/calendars/events/revectorize',
	} as const
	let isRevectorizingResource = $state<Record<ResourceKey, boolean>>({
		notes: false,
		threads: false,
		memories: false,
		reminders: false,
		calendar_events: false,
	})
	let revectorizeResourceResult = $state<Record<ResourceKey, RevectorizeResult | null>>({
		notes: null,
		threads: null,
		memories: null,
		reminders: null,
		calendar_events: null,
	})
	let revectorizeResourceError = $state<Record<ResourceKey, string | null>>({
		notes: null,
		threads: null,
		memories: null,
		reminders: null,
		calendar_events: null,
	})

	// delete state
	let showDeleteConfirm = $state(false)
	let deleteTarget = $state<string | null>(null)
	let isDeleting = $state(false)
	let showWipeConfirm = $state(false)
	let isWiping = $state(false)

	// collection detail
	let showDetailModal = $state(false)
	let detailCollection = $state<Record<string, unknown> | null>(null)
	let isFetchingDetail = $state(false)

	let totalPoints = $derived(collections.reduce((sum, c) => sum + c.points_count, 0))
	let totalVectors = $derived(collections.reduce((sum, c) => sum + c.vectors_count, 0))

	// -- data fetching --

	async function fetchCollections() {
		isFetching = true
		error = null
		try {
			const data = unwrap(await api.GET('/v1/vectorstores/collections' as const, {}))
			collections = data as unknown as CollectionInfo[]
		} catch (e) {
			console.error('failed to fetch collections', e)
			error = e instanceof Error ? e.message : 'failed to load collections'
		} finally {
			isFetching = false
		}
	}

	async function fetchCollectionDetail(name: string) {
		isFetchingDetail = true
		showDetailModal = true
		try {
			const data = unwrap(
				await api.GET('/v1/vectorstores/collections/{name}' as const, {
					params: { path: { name } },
				})
			)
			detailCollection = data as Record<string, unknown>
		} catch (e) {
			console.error('failed to fetch collection detail', e)
			detailCollection = { error: e instanceof Error ? e.message : 'failed to load' }
		} finally {
			isFetchingDetail = false
		}
	}

	// -- search --

	async function runSearch() {
		if (!searchQuery.trim()) return
		isSearching = true
		searchError = null
		searchResults = []
		try {
			const params = {
				q: searchQuery,
				limit: searchLimit,
				mode: searchMode as 'hybrid' | 'dense' | 'sparse' | 'autocomplete' | 'full',
				collection: searchCollection ?? undefined,
			}
			const data = unwrap(
				await api.POST('/v1/vectorstores/search' as const, {
					params: { query: params },
				})
			)
			searchResults = data as unknown as SearchResult[]
		} catch (e) {
			console.error('search failed', e)
			searchError = e instanceof Error ? e.message : 'search failed'
		} finally {
			isSearching = false
		}
	}

	// -- reindex --

	async function revectorizeAll() {
		isReindexing = true
		revectorizeResult = null
		try {
			const data = unwrap(await api.POST('/v1/vectorstores/revectorize' as const, {}))
			revectorizeResult = data as unknown as RevectorizeResult
			await fetchCollections()
		} catch (e) {
			console.error('revectorize failed', e)
			error = e instanceof Error ? e.message : 'revectorize failed'
		} finally {
			isReindexing = false
		}
	}

	async function revectorizeResource(resource: ResourceKey) {
		isRevectorizingResource[resource] = true
		revectorizeResourceResult[resource] = null
		revectorizeResourceError[resource] = null
		try {
			const endpoint = RESOURCE_ENDPOINTS[resource]
			const data = unwrap(await api.POST(endpoint, {}))
			revectorizeResourceResult[resource] = data as unknown as RevectorizeResult
			await fetchCollections()
		} catch (e) {
			console.error(`revectorize ${resource} failed`, e)
			revectorizeResourceError[resource] =
				e instanceof Error ? e.message : `revectorize ${resource} failed`
		} finally {
			isRevectorizingResource[resource] = false
		}
	}

	// -- delete --

	async function deleteCollection() {
		if (!deleteTarget) return
		isDeleting = true
		try {
			await api.DELETE('/v1/vectorstores/collections/{name}' as const, {
				params: { path: { name: deleteTarget } },
			})
			showDeleteConfirm = false
			deleteTarget = null
			await fetchCollections()
		} catch (e) {
			console.error('delete failed', e)
			error = e instanceof Error ? e.message : 'delete failed'
		} finally {
			isDeleting = false
		}
	}

	async function wipeAllCollections() {
		isWiping = true
		try {
			await api.DELETE('/v1/vectorstores/collections' as const, {})
			showWipeConfirm = false
			await fetchCollections()
		} catch (e) {
			console.error('wipe failed', e)
			error = e instanceof Error ? e.message : 'wipe failed'
		} finally {
			isWiping = false
		}
	}

	function confirmDelete(name: string) {
		deleteTarget = name
		showDeleteConfirm = true
	}

	onMount(() => {
		fetchCollections()
	})
</script>

<div class="flex h-full flex-col gap-6 overflow-y-auto">
	<!-- header -->
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">vector data</h2>
			<p class="text-zinc-400">
				manage vector collections, run diagnostic searches, and reindex data
			</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Button variant="outline" class="rounded-xl" onclick={() => (showSearchModal = true)}>
				<Search class="mr-2 h-4 w-4" />
				search
			</Button>
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={revectorizeAll}
				disabled={isReindexing}
			>
				<RefreshCw class="mr-2 h-4 w-4 {isReindexing ? 'animate-spin' : ''}" />
				{isReindexing ? 'revectorizing...' : 'revectorize all'}
			</Button>
			<Button
				variant="destructive"
				class="rounded-xl"
				onclick={() => (showWipeConfirm = true)}
				disabled={collections.length === 0}
			>
				<Trash2 class="mr-2 h-4 w-4" />
				wipe all
			</Button>
		</div>
	</div>

	<!-- reindex result -->
	{#if revectorizeResult}
		<Card class="border-green-800 bg-green-950/30">
			<CardContent class="py-3">
				<p class="text-sm text-green-400">
					revectorize complete —
					{Object.entries(revectorizeResult)
						.map(([k, v]) => `${k}: ${v}`)
						.join(', ')}
				</p>
			</CardContent>
		</Card>
	{/if}

	<!-- error -->
	{#if error}
		<Card class="border-red-800 bg-red-950/30">
			<CardContent class="py-3">
				<p class="text-sm text-red-400">{error}</p>
			</CardContent>
		</Card>
	{/if}

	<!-- per-resource revectorize -->
	<Card>
		<CardContent class="py-4">
			<p class="mb-3 text-sm font-medium text-zinc-300">revectorize by resource</p>
			<div class="flex flex-wrap gap-3">
				{#each RESOURCE_KEYS as resource (resource)}
					<div class="flex flex-col gap-1">
						<Button
							variant="outline"
							size="sm"
							onclick={() => revectorizeResource(resource)}
							disabled={isRevectorizingResource[resource]}
						>
							<RefreshCw
								class="mr-2 h-4 w-4 {isRevectorizingResource[resource]
									? 'animate-spin'
									: ''}"
							/>
							{isRevectorizingResource[resource] ? 'revectorizing...' : resource}
						</Button>
						{#if revectorizeResourceResult[resource]}
							<p class="text-xs text-green-400">
								{Object.entries(revectorizeResourceResult[resource]!)
									.map(([k, v]) => `${k}: ${v}`)
									.join(', ')}
							</p>
						{/if}
						{#if revectorizeResourceError[resource]}
							<p class="text-xs text-red-400">{revectorizeResourceError[resource]}</p>
						{/if}
					</div>
				{/each}
			</div>
		</CardContent>
	</Card>

	<!-- stats overview -->
	{#if !isFetching && collections.length > 0}
		<div class="grid grid-cols-3 gap-4">
			<Card>
				<CardContent class="py-4">
					<p class="text-sm text-zinc-400">collections</p>
					<p class="text-2xl font-semibold">{collections.length}</p>
				</CardContent>
			</Card>
			<Card>
				<CardContent class="py-4">
					<p class="text-sm text-zinc-400">total points</p>
					<p class="text-2xl font-semibold">{totalPoints.toLocaleString()}</p>
				</CardContent>
			</Card>
			<Card>
				<CardContent class="py-4">
					<p class="text-sm text-zinc-400">total vectors</p>
					<p class="text-2xl font-semibold">{totalVectors.toLocaleString()}</p>
				</CardContent>
			</Card>
		</div>
	{/if}

	<!-- collections list -->
	{#if isFetching}
		<NokodoLoader />
	{:else if collections.length === 0}
		<EmptyState
			message="no collections found"
			hint="collections are created when data is indexed. try reindexing."
		/>
	{:else}
		<div class="grid gap-3">
			{#each collections as col (col.name)}
				<Card
					class="cursor-pointer transition-colors hover:border-zinc-600"
					onclick={() => fetchCollectionDetail(col.name)}
				>
					<CardContent class="flex items-center justify-between py-4">
						<div class="flex items-center gap-4">
							<Database class="h-5 w-5 text-zinc-500" />
							<div>
								<p class="text-sm font-medium">{col.name}</p>
								<p class="text-xs text-zinc-500">
									{col.points_count.toLocaleString()} points -
									{col.vectors_count.toLocaleString()} vectors -
									{col.status}
								</p>
							</div>
						</div>
						<Button
							variant="ghost"
							size="sm"
							class="text-red-400 hover:text-red-300"
							onclick={(e: MouseEvent) => {
								e.stopPropagation()
								confirmDelete(col.name)
							}}
						>
							<Trash2 class="h-4 w-4" />
						</Button>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
</div>

<!-- search modal -->
<Dialog.Root bind:open={showSearchModal}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-4 shadow-xl sm:p-6"
		>
			<div class="mb-4 flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">search vectors</Dialog.Title>
				<Dialog.Close>
					<X class="h-4 w-4 text-zinc-400 hover:text-zinc-200" />
				</Dialog.Close>
			</div>

			<div class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div class="col-span-2">
						<Label>query</Label>
						<Input
							bind:value={searchQuery}
							placeholder="enter search query..."
							class="mt-1"
						/>
					</div>
					<div>
						<Label>collection</Label>
						<Select
							type="single"
							value={searchCollection ?? 'default'}
							onValueChange={(v: string) =>
								(searchCollection = v === 'default' ? null : v)}
						>
							<SelectTrigger class="mt-1">
								{searchCollection ?? 'default (auto)'}
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="default">default (auto)</SelectItem>
								{#each collections as col (col.name)}
									<SelectItem value={col.name}>{col.name}</SelectItem>
								{/each}
							</SelectContent>
						</Select>
					</div>
					<div>
						<Label>mode</Label>
						<Select
							type="single"
							value={searchMode}
							onValueChange={(v: string) => (searchMode = v)}
						>
							<SelectTrigger class="mt-1">{searchMode}</SelectTrigger>
							<SelectContent>
								<SelectItem value="hybrid">hybrid</SelectItem>
								<SelectItem value="dense">dense</SelectItem>
								<SelectItem value="sparse">sparse</SelectItem>
							</SelectContent>
						</Select>
					</div>
				</div>
				<div>
					<Label>limit</Label>
					<Input
						type="number"
						bind:value={searchLimit}
						min={1}
						max={100}
						class="mt-1 w-24"
					/>
				</div>
				<Button onclick={runSearch} disabled={isSearching || !searchQuery.trim()}>
					{isSearching ? 'searching...' : 'run search'}
				</Button>

				{#if searchError}
					<p class="text-sm text-red-400">{searchError}</p>
				{/if}

				{#if searchResults.length > 0}
					<div class="max-h-80 space-y-2 overflow-y-auto">
						{#each searchResults as result, i (result.id)}
							<Card>
								<CardContent class="py-3">
									<div class="flex items-start justify-between">
										<div class="flex-1">
											<p class="text-xs text-zinc-500">
												#{i + 1} - score: {result.score.toFixed(4)} - id: {result.id}
											</p>
											<p class="mt-1 text-sm">{result.content}</p>
											{#if Object.keys(result.metadata).length > 0}
												<p class="mt-1 text-xs text-zinc-500">
													{JSON.stringify(result.metadata)}
												</p>
											{/if}
										</div>
									</div>
								</CardContent>
							</Card>
						{/each}
					</div>
				{:else if !isSearching && searchQuery}
					<p class="text-sm text-zinc-500">no results</p>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<!-- collection detail modal -->
<Dialog.Root bind:open={showDetailModal}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-4 shadow-xl sm:p-6"
		>
			<div class="mb-4 flex items-center justify-between">
				<Dialog.Title class="text-lg font-semibold">collection details</Dialog.Title>
				<Dialog.Close>
					<X class="h-4 w-4 text-zinc-400 hover:text-zinc-200" />
				</Dialog.Close>
			</div>

			{#if isFetchingDetail}
				<NokodoLoader />
			{:else if detailCollection}
				<div class="space-y-3">
					{#each Object.entries(detailCollection) as [key, value] (key)}
						<div>
							<p class="text-xs font-medium text-zinc-400">{key}</p>
							<p class="text-sm">
								{typeof value === 'object'
									? JSON.stringify(value, null, 2)
									: String(value)}
							</p>
						</div>
					{/each}
				</div>
			{/if}
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<!-- delete confirm -->
<Dialog.Root bind:open={showDeleteConfirm}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-4 shadow-xl sm:p-6"
		>
			<Dialog.Title class="text-lg font-semibold">delete collection</Dialog.Title>
			<Dialog.Description class="mt-2 text-sm text-zinc-400">
				are you sure you want to delete <strong>{deleteTarget}</strong>? this action cannot
				be undone.
			</Dialog.Description>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="outline" size="sm" onclick={() => (showDeleteConfirm = false)}>
					cancel
				</Button>
				<Button
					variant="destructive"
					size="sm"
					onclick={deleteCollection}
					disabled={isDeleting}
				>
					{isDeleting ? 'deleting...' : 'delete'}
				</Button>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<!-- wipe all confirm -->
<Dialog.Root bind:open={showWipeConfirm}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[calc(100vh-2rem)] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-2xl border border-zinc-800 bg-zinc-900 p-4 shadow-xl sm:p-6"
		>
			<Dialog.Title class="text-lg font-semibold">wipe all collections</Dialog.Title>
			<Dialog.Description class="mt-2 text-sm text-zinc-400">
				this will permanently delete ALL {collections.length} collections. this cannot be undone.
				you will need to reindex everything afterwards.
			</Dialog.Description>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="outline" size="sm" onclick={() => (showWipeConfirm = false)}>
					cancel
				</Button>
				<Button
					variant="destructive"
					size="sm"
					onclick={wipeAllCollections}
					disabled={isWiping}
				>
					{isWiping ? 'wiping...' : 'wipe all'}
				</Button>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>
