<script lang="ts">
	import Grid from '$lib/components/icons/Grid.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import ChatWidget from '$lib/components/widgets/ChatWidget.svelte'
	import FileWidget from '$lib/components/widgets/FileWidget.svelte'
	import NoteWidget from '$lib/components/widgets/NoteWidget.svelte'
	import ProjectWidget from '$lib/components/widgets/ProjectWidget.svelte'
	import RemindersListWidget from '$lib/components/widgets/RemindersListWidget.svelte'
	import type {
		ResourceFilterMode,
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets/types'

	interface Props {
		resources: ResourceItem[]
		loading?: boolean
		layout?: ResourceLayoutMode
		filter?: ResourceFilterMode
		sort?: ResourceSortMode
		pageSize?: number
		emptyMessage?: string
		emptyIcon?: typeof Grid
		showLayoutToggle?: boolean
		showPagination?: boolean
		onItemEdit?: (item: ResourceItem) => void
		onItemDelete?: (item: ResourceItem) => Promise<boolean> | boolean | void
		class?: string
	}

	let {
		resources,
		loading = false,
		layout = $bindable<ResourceLayoutMode>('grid'),
		filter = 'all',
		sort = 'updated_at:desc',
		pageSize = 24,
		emptyMessage = 'no resources yet',
		showLayoutToggle = true,
		showPagination = true,
		onItemEdit,
		onItemDelete,
		class: className = '',
	}: Props = $props()

	let currentPage = $state(0)

	// filter resources by type
	const filtered = $derived.by(() => {
		if (filter === 'all') return resources
		const typeMap: Record<string, string[]> = {
			threads: ['thread'],
			notes: ['note'],
			reminders: ['reminder_list'],
			files: ['file'],
		}
		const allowedTypes = typeMap[filter] ?? []
		return resources.filter((r) => allowedTypes.includes(r.type))
	})

	// sort resources
	const sorted = $derived.by(() => {
		const [sortBy, sortDir] = sort.split(':') as [string, string]
		const items = [...filtered]
		items.sort((a, b) => {
			let cmp = 0
			if (sortBy === 'title') {
				cmp = (a.title || '').localeCompare(b.title || '')
			} else if (sortBy === 'created_at') {
				cmp = a.createdAt - b.createdAt
			} else {
				cmp = a.updatedAt - b.updatedAt
			}
			return sortDir === 'desc' ? -cmp : cmp
		})
		return items
	})

	// paginate
	const totalPages = $derived(Math.max(1, Math.ceil(sorted.length / pageSize)))
	const paginated = $derived(sorted.slice(currentPage * pageSize, (currentPage + 1) * pageSize))

	// reset page when filter/sort changes
	$effect(() => {
		filter
		sort
		currentPage = 0
	})

	function prevPage() {
		if (currentPage > 0) currentPage--
	}

	function nextPage() {
		if (currentPage < totalPages - 1) currentPage++
	}
</script>

<div class="flex flex-col gap-4 {className}">
	{#if showLayoutToggle}
		<div class="flex items-center justify-end gap-1">
			<button
				type="button"
				class="flex size-8 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent transition-colors duration-150 {layout ===
				'grid'
					? 'text-foreground/80'
					: 'text-foreground/30 hover:text-foreground/50'}"
				onclick={() => (layout = 'grid')}
				aria-label="grid view"
				aria-pressed={layout === 'grid'}
			>
				<Grid class="size-4" />
			</button>
			<button
				type="button"
				class="flex size-8 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent transition-colors duration-150 {layout ===
				'list'
					? 'text-foreground/80'
					: 'text-foreground/30 hover:text-foreground/50'}"
				onclick={() => (layout = 'list')}
				aria-label="list view"
				aria-pressed={layout === 'list'}
			>
				<ListBullet class="size-4" />
			</button>
		</div>
	{/if}

	{#if loading}
		<div
			class={layout === 'grid'
				? 'grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4'
				: 'flex flex-col gap-2'}
		>
			{#each { length: 6 } as _}
				<div
					class="liquid-glass liquid-glass--frosted animate-pulse overflow-hidden rounded-2xl {layout ===
					'grid'
						? 'h-52'
						: 'h-16'}"
				></div>
			{/each}
		</div>
	{:else if paginated.length === 0}
		<div
			class="liquid-glass liquid-glass--frosted flex flex-1 flex-col items-center justify-center overflow-hidden rounded-2xl py-16 text-center"
		>
			<p class="text-sm text-foreground/50">{emptyMessage}</p>
		</div>
	{:else}
		<div
			class={layout === 'grid'
				? 'grid grid-cols-[repeat(auto-fill,minmax(340px,1fr))] gap-4'
				: 'flex flex-col gap-2'}
		>
			{#each paginated as resource (resource.id)}
				{#if resource.type === 'thread'}
					<ChatWidget {resource} {layout} />
				{:else if resource.type === 'note'}
					<NoteWidget {resource} {layout} />
				{:else if resource.type === 'reminder_list'}
					<RemindersListWidget {resource} {layout} />
				{:else if resource.type === 'project'}
					<ProjectWidget
						{resource}
						{layout}
						onEdit={onItemEdit ? () => onItemEdit(resource) : undefined}
						onDelete={onItemDelete ? () => onItemDelete(resource) : undefined}
					/>
				{:else if resource.type === 'file'}
					<FileWidget {resource} {layout} />
				{/if}
			{/each}
		</div>
	{/if}

	{#if showPagination && totalPages > 1}
		<div class="flex items-center justify-center gap-3 pt-2">
			<button
				type="button"
				class="rounded-pill cursor-pointer border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-xs text-foreground/60 transition-colors duration-150 hover:bg-foreground/10 disabled:cursor-default disabled:opacity-30"
				onclick={prevPage}
				disabled={currentPage === 0}
			>
				previous
			</button>
			<span class="text-xs text-foreground/40">
				{currentPage + 1} / {totalPages}
			</span>
			<button
				type="button"
				class="rounded-pill cursor-pointer border border-foreground/10 bg-foreground/5 px-3 py-1.5 text-xs text-foreground/60 transition-colors duration-150 hover:bg-foreground/10 disabled:cursor-default disabled:opacity-30"
				onclick={nextPage}
				disabled={currentPage >= totalPages - 1}
			>
				next
			</button>
		</div>
	{/if}
</div>
