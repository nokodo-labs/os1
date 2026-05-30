<script lang="ts">
	import { browser } from '$app/environment'
	import { page } from '$app/state'
	import { api, unwrap, type Schemas } from '$lib/api'

	type Prompt = Schemas['Prompt']

	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import PromptVariablesLegend from '$lib/components/PromptVariablesLegend.svelte'
	import { Button } from '$lib/components/ui/button'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import {
		ArrowDown,
		ArrowUp,
		BookOpen,
		ChevronLeft,
		ChevronRight,
		Clock,
		Hash,
		Plus,
		RefreshCw,
		Save,
		Terminal,
		Trash2,
		X,
	} from '@lucide/svelte'
	import { Dialog } from 'bits-ui'
	import { SvelteURLSearchParams } from 'svelte/reactivity'

	type SortKey = 'updated_at' | 'created_at' | 'command'
	type SortDir = 'asc' | 'desc'

	const sortOptions: Array<{ value: SortKey; label: string }> = [
		{ value: 'updated_at', label: 'updated at' },
		{ value: 'created_at', label: 'created at' },
		{ value: 'command', label: 'command' },
	]

	function defaultSortDir(sort: SortKey): SortDir {
		if (sort === 'command') return 'asc'
		return 'desc'
	}

	const DEFAULT_SORT: SortKey = 'updated_at'
	const SORT_PARAM = 'sort'
	const SORT_DIR_PARAM = 'sort_dir'

	let sortKey = $state<SortKey>(DEFAULT_SORT)
	let sortDir = $state<SortDir>(defaultSortDir(DEFAULT_SORT))
	let pageIndex = $state(0)
	let limit = $state(20)
	let refreshToken = $state(0)

	let prompts = $state<Prompt[]>([])
	let isLoading = $state(false)
	let isSaving = $state(false)
	let isDeleting = $state(false)
	let error = $state<string | null>(null)
	let modalError = $state<string | null>(null)
	let hasNext = $state(false)

	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let editingId = $state<string | null>(null)
	let formCommand = $state('')
	let formContent = $state('')
	let showVariablesLegend = $state(false)

	function replaceUrl(target: string) {
		if (!browser) return
		history.replaceState(history.state, '', target)
	}

	function updateQueryParams(updates: Record<string, string | null>) {
		if (!browser) return
		const url = page.url
		const params = new SvelteURLSearchParams(url.searchParams)
		for (const [key, value] of Object.entries(updates)) {
			if (!value) params.delete(key)
			else params.set(key, value)
		}
		const qs = params.toString()
		replaceUrl(qs ? `${url.pathname}?${qs}` : url.pathname)
	}

	function setSort(next: SortKey) {
		sortKey = next
		sortDir = defaultSortDir(next)
		pageIndex = 0
		updateQueryParams({ [SORT_PARAM]: next, [SORT_DIR_PARAM]: sortDir })
	}

	function toggleSortDir() {
		const next = sortDir === 'asc' ? 'desc' : 'asc'
		sortDir = next
		pageIndex = 0
		updateQueryParams({ [SORT_DIR_PARAM]: next })
	}

	function refresh() {
		refreshToken += 1
	}

	// Sync sort from URL params
	$effect(() => {
		if (!browser) return

		const sp = page.url.searchParams
		const sort = sp.get(SORT_PARAM)
		const nextSort =
			sort && sortOptions.some((o) => o.value === sort) ? (sort as SortKey) : DEFAULT_SORT
		const dir = sp.get(SORT_DIR_PARAM)
		const nextDir = dir === 'asc' || dir === 'desc' ? dir : defaultSortDir(nextSort)

		if (sortKey !== nextSort || sortDir !== nextDir) {
			sortKey = nextSort
			sortDir = nextDir
			pageIndex = 0
		}
	})

	// Load prompts with pagination
	$effect(() => {
		if (!browser) return

		const skip = pageIndex * limit + refreshToken * 0

		isLoading = true
		error = null
		api.GET('/v1/prompts', {
			params: { query: { skip, limit, sort_by: sortKey, sort_dir: sortDir } },
		})
			.then((r) => unwrap(r))
			.then((result) => {
				prompts = result
				hasNext = result.length === limit
			})
			.catch((e: unknown) => {
				error = e instanceof Error ? e.message : 'failed to load prompts'
				prompts = []
				hasNext = false
			})
			.finally(() => {
				isLoading = false
			})
	})

	function openCreateModal() {
		modalMode = 'create'
		editingId = null
		formCommand = ''
		formContent = ''
		modalError = null
		showModal = true
	}

	function openEditModal(prompt: Prompt) {
		modalMode = 'edit'
		editingId = prompt.id
		formCommand = prompt.command
		formContent = prompt.content
		modalError = null
		showModal = true
	}

	function closeModal() {
		showModal = false
		modalError = null
	}

	async function handleSave() {
		const trimmedCommand = formCommand.trim().replace(/\s+/g, '-')
		if (!trimmedCommand) {
			modalError = 'command is required'
			return
		}
		if (!formContent.trim()) {
			modalError = 'content is required'
			return
		}

		isSaving = true
		modalError = null
		try {
			if (modalMode === 'edit' && editingId) {
				await unwrap(
					await api.PATCH('/v1/prompts/{prompt_id}', {
						params: { path: { prompt_id: editingId } },
						body: {
							command: trimmedCommand,
							content: formContent,
						},
					})
				)
			} else {
				await unwrap(
					await api.POST('/v1/prompts', {
						body: {
							command: trimmedCommand,
							content: formContent,
						},
					})
				)
			}
			refresh()
			closeModal()
		} catch (e: unknown) {
			modalError = e instanceof Error ? e.message : 'failed to save prompt'
		} finally {
			isSaving = false
		}
	}

	async function handleDelete(promptId: string) {
		const ok = confirm('delete this prompt? this cannot be undone.')
		if (!ok) return

		isDeleting = true
		error = null
		try {
			await unwrap(
				await api.DELETE('/v1/prompts/{prompt_id}', {
					params: { path: { prompt_id: promptId } },
				})
			)
			refresh()
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'failed to delete prompt'
		} finally {
			isDeleting = false
		}
	}

	function preview(text: string, maxLen = 180) {
		const normalized = text.replace(/\s+/g, ' ').trim()
		if (normalized.length <= maxLen) return normalized
		return normalized.slice(0, maxLen) + '…'
	}
</script>

<div class="flex min-h-0 flex-1 flex-col gap-6">
	<div class="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div>
			<h2 class="text-2xl font-bold tracking-tight">prompts</h2>
			<p class="text-zinc-400">write and iterate on prompts.</p>
		</div>
		<div class="flex flex-wrap items-center gap-2">
			<Button class="gap-2 rounded-xl" onclick={openCreateModal}>
				<Plus class="h-4 w-4" />
				create prompt
			</Button>
			<Select value={sortKey} onValueChange={(v: string) => setSort(v as SortKey)}>
				<SelectTrigger class="w-56 rounded-xl">
					<span class="truncate text-left">
						{sortOptions.find((o) => o.value === sortKey)?.label ?? sortKey}
					</span>
				</SelectTrigger>
				<SelectContent>
					{#each sortOptions as opt (opt.value)}
						<SelectItem value={opt.value}>{opt.label}</SelectItem>
					{/each}
				</SelectContent>
			</Select>
			<Button
				variant="outline"
				class="rounded-xl px-3"
				onclick={() => toggleSortDir()}
				disabled={isLoading}
				title="toggle sort direction"
				aria-label="toggle sort direction"
			>
				{#if sortDir === 'asc'}
					<ArrowUp class="h-4 w-4" />
				{:else}
					<ArrowDown class="h-4 w-4" />
				{/if}
			</Button>
			<Button
				variant="outline"
				class="rounded-xl"
				onclick={() => refresh()}
				disabled={isLoading}
			>
				<RefreshCw class="mr-1.5 h-4 w-4" />
				refresh
			</Button>
		</div>
	</div>

	{#if error}
		<div
			class="shrink-0 rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200"
		>
			{error}
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
					page {pageIndex + 1}{prompts.length > 0
						? ` \u00b7 ${prompts.length} items`
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
			{#if isLoading && prompts.length === 0}
				<div
					class="flex min-h-0 flex-1 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
				>
					<NokodoLoader />
				</div>
			{:else if prompts.length === 0}
				<div
					class="rounded-xl border border-dashed border-zinc-800 p-10 text-center text-sm text-zinc-500"
				>
					no prompts yet
				</div>
			{:else}
				<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{#each prompts as p (p.id)}
						<div
							role="button"
							tabindex="0"
							class="flex w-full cursor-pointer flex-col justify-between gap-4 rounded-2xl border border-zinc-800 bg-zinc-900 p-4 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-800/50"
							onclick={() => openEditModal(p)}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault()
									openEditModal(p)
								}
							}}
						>
							<div class="flex items-start justify-between gap-4">
								<div class="flex min-w-0 flex-1 items-start gap-4">
									<div
										class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-fuchsia-500/15 text-fuchsia-400"
									>
										<Terminal class="h-5 w-5" />
									</div>
									<div class="min-w-0 flex-1 space-y-1">
										<span class="truncate text-base font-medium text-zinc-100"
											>{p.command}</span
										>
										<div
											class="flex items-center gap-1.5 font-mono text-[10px] opacity-50"
										>
											<Hash class="h-3 w-3" />
											{p.id}
										</div>
									</div>
								</div>
								<div class="flex shrink-0 gap-1">
									<Button
										variant="ghost"
										size="icon"
										class="h-8 w-8 text-zinc-400 hover:bg-red-500/10 hover:text-red-500"
										onclick={(e: Event) => {
											e.stopPropagation()
											handleDelete(p.id)
										}}
										disabled={isDeleting}
									>
										<Trash2 class="h-4 w-4" />
									</Button>
								</div>
							</div>
							<div class="font-mono text-xs whitespace-pre-wrap text-zinc-400">
								{preview(p.content)}
							</div>
							<div class="shrink-0 text-xs text-zinc-500">
								<div class="flex items-center gap-1.5 whitespace-nowrap">
									<Clock class="h-3.5 w-3.5" />
									updated {new Date(p.updated_at).toLocaleString()}
								</div>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<Dialog.Root
	bind:open={showModal}
	onOpenChange={(v) => {
		if (!v) closeModal()
	}}
>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 z-50 bg-black/60" />
		<Dialog.Content
			data-dialog-content
			class="fixed top-1/2 left-1/2 z-50 flex max-h-[90vh] w-[min(768px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-lg"
		>
			<div
				class="flex shrink-0 items-center justify-between border-b border-zinc-800 px-6 py-4"
			>
				<div>
					<Dialog.Title class="text-lg font-semibold">
						{modalMode === 'create' ? 'create prompt' : 'edit prompt'}
					</Dialog.Title>
					<Dialog.Description class="text-sm text-zinc-400">
						command + content
					</Dialog.Description>
				</div>
				<Button variant="ghost" size="icon" class="rounded-xl" onclick={closeModal}>
					<X class="h-4 w-4" />
				</Button>
			</div>
			<form
				onsubmit={(e) => {
					e.preventDefault()
					handleSave()
				}}
			>
				<div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-4">
					{#if modalError}
						<div
							class="rounded-xl border border-red-900/50 bg-red-900/10 p-3 text-sm text-red-200"
						>
							{modalError}
						</div>
					{/if}

					{#if modalMode === 'edit' && editingId}
						<div class="space-y-1">
							<Label class="text-xs text-zinc-500">id</Label>
							<p class="font-mono text-xs text-zinc-400 select-all">{editingId}</p>
						</div>
					{/if}

					<div class="space-y-2">
						<Label for="command">command</Label>
						<Input
							id="command"
							bind:value={formCommand}
							placeholder="e.g. summarize"
							class="rounded-xl"
							oninput={() => {
								formCommand = formCommand.replace(/\s+/g, '-')
							}}
						/>
						<p class="text-xs text-zinc-500">
							letters, numbers, and dashes only. spaces are auto-converted to dashes.
						</p>
					</div>
					<div class="space-y-2">
						<div class="flex items-center justify-between">
							<Label for="content">content</Label>
							<Button
								type="button"
								variant="ghost"
								size="sm"
								class="h-7 gap-1 text-xs text-zinc-400 hover:text-zinc-200"
								onclick={() => (showVariablesLegend = true)}
							>
								<BookOpen class="h-3.5 w-3.5" />
								variables
							</Button>
						</div>
						<textarea
							id="content"
							bind:value={formContent}
							rows={16}
							placeholder="write your prompt..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 font-mono text-sm"
						></textarea>
					</div>
				</div>
				<div class="flex shrink-0 justify-end gap-2 border-t border-zinc-800 px-6 py-4">
					<Button
						type="button"
						variant="outline"
						class="rounded-xl"
						onclick={closeModal}
						disabled={isSaving}
					>
						<X class="mr-1.5 h-4 w-4" />
						cancel
					</Button>
					<Button type="submit" class="rounded-xl" disabled={isSaving}>
						<Save class="mr-1.5 h-4 w-4" />
						{isSaving ? 'saving...' : modalMode === 'create' ? 'create' : 'save'}
					</Button>
				</div>
			</form>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<PromptVariablesLegend bind:open={showVariablesLegend} {prompts} />
