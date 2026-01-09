<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { page } from '$app/stores'
	import { PromptsService, type Prompt } from '$lib/api'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { Button } from '$lib/components/ui/button'
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle,
	} from '$lib/components/ui/card'
	import { Input } from '$lib/components/ui/input'
	import { Label } from '$lib/components/ui/label'
	import { Select, SelectContent, SelectItem, SelectTrigger } from '$lib/components/ui/select'
	import { ArrowDown, ArrowUp, Pencil, Plus, Trash2 } from '@lucide/svelte'

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
	let hasNext = $state(false)

	let showModal = $state(false)
	let modalMode = $state<'create' | 'edit'>('create')
	let editingId = $state<string | null>(null)
	let formCommand = $state('')
	let formContent = $state('')

	function updateQueryParams(updates: Record<string, string | null>) {
		if (!browser) return
		const url = $page.url
		const params = new URLSearchParams(url.searchParams)
		for (const [key, value] of Object.entries(updates)) {
			if (!value) params.delete(key)
			else params.set(key, value)
		}
		const qs = params.toString()
		goto(qs ? `${url.pathname}?${qs}` : url.pathname, {
			replaceState: true,
			keepFocus: true,
			noScroll: true,
		})
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

		const sp = $page.url.searchParams
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

		const skip = pageIndex * limit
		sortKey
		sortDir
		refreshToken

		isLoading = true
		error = null
		PromptsService.listPromptsPromptsGet(skip, limit, sortKey, sortDir)
			.then((result) => {
				prompts = result
				hasNext = result.length === limit
			})
			.catch((e: any) => {
				error = e?.message ?? 'failed to load prompts'
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
		showModal = true
	}

	function openEditModal(prompt: Prompt) {
		modalMode = 'edit'
		editingId = prompt.id
		formCommand = prompt.command
		formContent = prompt.content
		showModal = true
	}

	function closeModal() {
		showModal = false
	}

	async function handleSave() {
		const trimmedCommand = formCommand.trim()
		if (!trimmedCommand) {
			error = 'command is required'
			return
		}
		if (!formContent.trim()) {
			error = 'content is required'
			return
		}

		isSaving = true
		error = null
		try {
			if (modalMode === 'edit' && editingId) {
				await PromptsService.updatePromptPromptsPromptIdPatch(editingId, {
					command: trimmedCommand,
					content: formContent,
				})
			} else {
				await PromptsService.createPromptPromptsPost({
					command: trimmedCommand,
					content: formContent,
				})
			}
			refresh()
			closeModal()
		} catch (e: any) {
			error = e?.message ?? 'failed to save prompt'
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
			await PromptsService.deletePromptPromptsPromptIdDelete(promptId)
			refresh()
		} catch (e: any) {
			error = e?.message ?? 'failed to delete prompt'
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

<div class="space-y-6">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
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
				{isLoading ? 'loading...' : 'refresh'}
			</Button>
		</div>
	</div>

	{#if error}
		<div class="rounded-2xl border border-red-900/50 bg-red-900/10 p-4 text-sm text-red-200">
			{error}
		</div>
	{/if}

	<Card class="rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
		<CardHeader class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
			<div>
				<CardTitle>list</CardTitle>
				<CardDescription>
					page {pageIndex + 1} · showing {prompts.length}{hasNext ? '+' : ''}
				</CardDescription>
			</div>
			<div class="flex items-center gap-2">
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex = Math.max(0, pageIndex - 1)
					}}
					disabled={pageIndex === 0 || isLoading}
				>
					prev
				</Button>
				<Button
					variant="outline"
					class="rounded-xl"
					onclick={() => {
						pageIndex += 1
					}}
					disabled={!hasNext || isLoading}
				>
					next
				</Button>
			</div>
		</CardHeader>
		<CardContent class="space-y-2">
			{#if isLoading && prompts.length === 0}
				<div
					class="flex items-center justify-center rounded-xl border border-zinc-800 bg-zinc-950 p-10"
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
				{#each prompts as p (p.id)}
					<div
						class="rounded-xl border border-zinc-800 bg-zinc-950 p-4 transition-colors hover:border-zinc-700"
					>
						<div
							class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
						>
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2">
									<span class="truncate font-medium">{p.command}</span>
								</div>
								<div
									class="mt-2 font-mono text-xs whitespace-pre-wrap text-zinc-400"
								>
									{preview(p.content)}
								</div>
								<div class="mt-2 text-xs text-zinc-500">
									id: {p.id}
								</div>
							</div>
							<div class="flex shrink-0 items-start gap-2">
								<div class="text-xs text-zinc-500">
									<div>updated {new Date(p.updated_at).toLocaleString()}</div>
									<div>created {new Date(p.created_at).toLocaleString()}</div>
								</div>
								<div class="flex gap-1">
									<Button
										variant="ghost"
										size="icon"
										class="h-8 w-8 text-zinc-400 hover:text-zinc-100"
										onclick={() => openEditModal(p)}
									>
										<Pencil class="h-4 w-4" />
									</Button>
									<Button
										variant="ghost"
										size="icon"
										class="h-8 w-8 text-zinc-400 hover:text-red-500"
										onclick={() => handleDelete(p.id)}
										disabled={isDeleting}
									>
										<Trash2 class="h-4 w-4" />
									</Button>
								</div>
							</div>
						</div>
					</div>
				{/each}
			{/if}
		</CardContent>
	</Card>
</div>

{#if showModal}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
	>
		<Card class="w-full max-w-3xl rounded-2xl border-zinc-800 bg-zinc-900 text-zinc-100">
			<CardHeader>
				<CardTitle>{modalMode === 'create' ? 'create prompt' : 'edit prompt'}</CardTitle>
				<CardDescription>command + content</CardDescription>
			</CardHeader>
			<form
				onsubmit={(e) => {
					e.preventDefault()
					handleSave()
				}}
			>
				<CardContent class="max-h-[70vh] space-y-4 overflow-y-auto pr-2">
					<div class="space-y-2">
						<Label for="command">command</Label>
						<Input
							id="command"
							bind:value={formCommand}
							placeholder="e.g. /summarize"
							class="rounded-xl"
						/>
					</div>
					<div class="space-y-2">
						<Label for="content">content</Label>
						<textarea
							id="content"
							bind:value={formContent}
							rows={16}
							placeholder="write your prompt..."
							class="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm"
						></textarea>
					</div>
				</CardContent>
				<div class="flex justify-end gap-2 border-t border-zinc-800 p-4">
					<Button
						type="button"
						variant="outline"
						class="rounded-xl"
						onclick={closeModal}
						disabled={isSaving}
					>
						cancel
					</Button>
					<Button type="submit" class="rounded-xl" disabled={isSaving}>
						{isSaving ? 'saving...' : 'save'}
					</Button>
				</div>
			</form>
		</Card>
	</div>
{/if}
