<script lang="ts">
	import { browser } from '$app/environment'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import FloatingScrollTopButton from '$lib/components/FloatingScrollTopButton.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import {
		resourceAccess,
		type AccessControlledResourceType,
	} from '$lib/stores/resourceAccess.svelte'
	import Grid from '$lib/components/icons/Grid.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import LoadingMoreIndicator from '$lib/components/LoadingMoreIndicator.svelte'
	import CalendarWidget from '$lib/components/widgets/CalendarWidget.svelte'
	import ChatWidget from '$lib/components/widgets/ChatWidget.svelte'
	import FileWidget from '$lib/components/widgets/FileWidget.svelte'
	import NoteWidget from '$lib/components/widgets/NoteWidget.svelte'
	import ProjectWidget from '$lib/components/widgets/ProjectWidget.svelte'
	import RemindersListWidget from '$lib/components/widgets/RemindersListWidget.svelte'
	import ResourceActionMenu from '$lib/components/widgets/ResourceActionMenu.svelte'
	import ResourceWidget from '$lib/components/widgets/ResourceWidget.svelte'
	import type {
		ResourceFilterMode,
		ResourceItem,
		ResourceLayoutMode,
		ResourceSortMode,
	} from '$lib/components/widgets/types'
	import { session } from '$lib/stores/session.svelte'

	type ResourceViewLayout = ResourceLayoutMode | 'pill'

	type ResourceProjectOption = {
		id: string
		name: string
		owner_id: string
	}

	interface Props {
		resources: ResourceItem[]
		loading?: boolean
		layout?: ResourceViewLayout
		listVariant?: 'default' | 'pill'
		filter?: ResourceFilterMode
		sort?: ResourceSortMode | 'none'
		pageSize?: number
		emptyMessage?: string
		emptyIcon?: typeof Grid
		showLayoutToggle?: boolean
		showPagination?: boolean
		currentUserId?: string | null
		ownedSectionLabel?: string
		sharedSectionLabel?: string
		ownedEmptyMessage?: string
		sharedEmptyMessage?: string
		showOwnershipSections?: boolean
		showScrollTopButton?: boolean
		scrollTopButtonBottom?: string
		onItemEdit?: (item: ResourceItem) => void
		onItemShare?: (item: ResourceItem) => void
		onItemDelete?: (item: ResourceItem) => Promise<boolean> | boolean | void
		onItemRemoveFromProject?: (item: ResourceItem) => Promise<void> | void
		onItemProjectToggle?: (
			item: ResourceItem,
			projectId: string,
			selected: boolean
		) => Promise<void> | void
		onItemClick?: (item: ResourceItem) => void
		projectOptions?: ResourceProjectOption[]
		getItemProjectIds?: (item: ResourceItem) => string[]
		ownedSectionCount?: number | null
		sharedSectionCount?: number | null
		onLoadMore?: () => void | Promise<void>
		hasMore?: boolean
		loadingMore?: boolean
		class?: string
	}

	let {
		resources,
		loading = false,
		layout = $bindable<ResourceViewLayout>('grid'),
		listVariant = 'default',
		filter = 'all',
		sort = 'updated_at:desc',
		pageSize = 24,
		emptyMessage = 'no resources yet',
		showLayoutToggle = true,
		showPagination = true,
		currentUserId = null,
		ownedSectionLabel = 'yours',
		sharedSectionLabel = 'shared with you',
		ownedEmptyMessage = emptyMessage,
		sharedEmptyMessage = 'nothing shared with you',
		showOwnershipSections = true,
		showScrollTopButton = true,
		scrollTopButtonBottom = '1.5rem',
		onItemEdit,
		onItemShare,
		onItemDelete,
		onItemRemoveFromProject,
		onItemProjectToggle,
		onItemClick,
		projectOptions = [],
		getItemProjectIds,
		ownedSectionCount = null,
		sharedSectionCount = null,
		onLoadMore,
		hasMore = false,
		loadingMore = false,
		class: className = '',
	}: Props = $props()

	type ResourceVirtualRow =
		| {
				kind: 'section'
				id: string
				label: string
				count: number
				open: boolean
				target: 'owned' | 'shared'
		  }
		| { kind: 'empty'; id: string; message: string }
		| { kind: 'resources'; id: string; items: ResourceItem[] }
		| { kind: 'loading'; id: string }

	const GRID_MIN_WIDTH = 340
	const BIG_PHONE_GRID_MIN_WIDTH = 190
	const BIG_PHONE_GRID_MIN_VIEWPORT = 420
	const TABLET_GRID_MIN_VIEWPORT = 640
	const GRID_GAP = 16
	const PAGE_LOAD_MORE_THRESHOLD = 720

	let currentPage = $state(0)
	let ownedSectionOpen = $state(true)
	let sharedSectionOpen = $state(true)
	let rootEl = $state<HTMLDivElement | null>(null)
	let virtualCollectionEl: HTMLDivElement | null = $state(null)
	let pageScrollTarget = $state<HTMLElement | null>(null)
	let virtualGridColumns = $state(1)
	let lastAccessPrefetchKey = ''
	let loadMoreInFlight: Promise<void> | null = null
	const resourceGridClass = 'resource-grid grid gap-4'
	const virtualGridRowStyle = $derived(
		`grid-template-columns: repeat(${virtualGridColumns}, minmax(0, 1fr));`
	)

	// filter resources by type
	const filtered = $derived.by(() => {
		if (filter === 'all') return resources
		const typeMap: Record<string, string[]> = {
			threads: ['thread'],
			notes: ['note'],
			reminders: ['reminder', 'reminder_list'],
			files: ['file'],
			projects: ['project'],
			calendars: ['calendar_event', 'calendar'],
		}
		const allowedTypes = typeMap[filter] ?? []
		return resources.filter((r) => allowedTypes.includes(r.type))
	})

	// sort resources
	const sorted = $derived.by(() => {
		if (sort === 'none') return [...filtered]
		const [sortBy, sortDir] = sort.split(':') as [string, string]
		const items = [...filtered]
		items.sort((a, b) => {
			let cmp: number
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

	// paginate (only used when onLoadMore is NOT provided - client-side mode)
	const useInfiniteScroll = $derived(!!onLoadMore)
	const effectiveLayout = $derived<ResourceViewLayout>(
		layout === 'list' && listVariant === 'pill' ? 'pill' : layout
	)
	const concreteLayout = $derived<ResourceLayoutMode>(layout === 'grid' ? 'grid' : 'list')
	const totalPages = $derived(Math.max(1, Math.ceil(sorted.length / pageSize)))
	const paginated = $derived(
		useInfiniteScroll
			? sorted
			: sorted.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
	)
	const sharedResources = $derived(
		currentUserId ? paginated.filter((resource) => isSharedResource(resource)) : []
	)
	const ownedResources = $derived(
		currentUserId ? paginated.filter((resource) => !isSharedResource(resource)) : paginated
	)
	const showSharedSections = $derived(Boolean(currentUserId && showOwnershipSections))
	const displayedOwnedSectionCount = $derived(ownedSectionCount ?? ownedResources.length)
	const displayedSharedSectionCount = $derived(sharedSectionCount ?? sharedResources.length)
	const effectiveSharedSectionOpen = $derived(
		displayedSharedSectionCount > 0 ? sharedSectionOpen : false
	)
	const hasGenericActions = $derived(
		Boolean(
			onItemEdit ||
			onItemShare ||
			onItemDelete ||
			onItemRemoveFromProject ||
			onItemProjectToggle
		)
	)
	const virtualRows = $derived.by(() => buildVirtualRows())

	// reset page when filter/sort changes
	$effect(() => {
		const key = `${filter}:${sort}`
		if (key) currentPage = 0
	})

	$effect(() => {
		const el = virtualCollectionEl
		if (!el || layout !== 'grid') {
			virtualGridColumns = 1
			return
		}

		const updateColumns = () => {
			const width = el.getBoundingClientRect().width
			if (!Number.isFinite(width) || width <= 0) return
			const viewportWidth = window.visualViewport?.width ?? window.innerWidth
			const minWidth =
				viewportWidth >= BIG_PHONE_GRID_MIN_VIEWPORT &&
				viewportWidth < TABLET_GRID_MIN_VIEWPORT
					? BIG_PHONE_GRID_MIN_WIDTH
					: GRID_MIN_WIDTH
			const nextColumns = Math.max(1, Math.floor((width + GRID_GAP) / (minWidth + GRID_GAP)))
			if (nextColumns !== virtualGridColumns) virtualGridColumns = nextColumns
		}

		updateColumns()
		const observer = new ResizeObserver(updateColumns)
		observer.observe(el)
		window.addEventListener('resize', updateColumns)
		return () => {
			observer.disconnect()
			window.removeEventListener('resize', updateColumns)
		}
	})

	$effect(() => {
		if (!currentUserId) return
		const accessVersion = resourceAccess.version
		const resourcesToPrefetch = paginated
		const prefetchKey =
			`${accessVersion}:` +
			resourcesToPrefetch
				.map(
					(resource) =>
						`${resource.type}:${resource.id}:${resourceOwnerId(resource) ?? ''}`
				)
				.join('|')
		if (prefetchKey === lastAccessPrefetchKey) return
		lastAccessPrefetchKey = prefetchKey

		const ownerIds = resourcesToPrefetch
			.map(resourceOwnerId)
			.filter((ownerId): ownerId is string => Boolean(ownerId && ownerId !== currentUserId))
		if (ownerIds.length > 0) void session.ensureUsers(ownerIds)
		for (const resource of resourcesToPrefetch) {
			const accessType = accessResourceType(resource.type)
			if (accessType) {
				void resourceAccess.ensure(accessType, resource.id, resourceOwnerId(resource))
			}
		}
	})

	$effect(() => {
		if (!browser || !rootEl) {
			pageScrollTarget = null
			return
		}
		pageScrollTarget = resolvePageScrollTarget(rootEl)
	})

	$effect(() => {
		const target = pageScrollTarget
		if (!browser || !target || !useInfiniteScroll) return

		const onScroll = () => maybeLoadMoreFromPage(target)
		target.addEventListener('scroll', onScroll, { passive: true })
		const frame = requestAnimationFrame(onScroll)
		return () => {
			target.removeEventListener('scroll', onScroll)
			cancelAnimationFrame(frame)
		}
	})

	$effect(() => {
		const target = pageScrollTarget
		if (!target || !useInfiniteScroll || !hasMore || loadingMore) return
		maybeLoadMoreFromPage(target)
	})

	function prevPage() {
		if (currentPage > 0) currentPage--
	}

	function nextPage() {
		if (currentPage < totalPages - 1) currentPage++
	}

	/** Return the owner id embedded in resource metadata. */
	function resourceOwnerId(resource: ResourceItem): string | null {
		const ownerId = resource.meta?.owner_id
		return typeof ownerId === 'string' && ownerId.length > 0 ? ownerId : null
	}

	/** Return the access-controlled container type for a displayed resource. */
	function accessResourceType(type: ResourceItem['type']): AccessControlledResourceType | null {
		switch (type) {
			case 'thread':
			case 'note':
			case 'reminder_list':
			case 'calendar':
			case 'file':
			case 'project':
				return type
			case 'reminder':
			case 'calendar_event':
				return null
		}
	}

	function isSharedResource(resource: ResourceItem): boolean {
		const ownerId = resourceOwnerId(resource)
		return Boolean(currentUserId && ownerId && ownerId !== currentUserId)
	}

	function resolvePageScrollTarget(node: HTMLElement): HTMLElement | null {
		const scrollContainer = findScrollContainer(node)
		if (scrollContainer) return scrollContainer
		const main = node.closest('[role="main"]')
		if (main instanceof HTMLElement) return main
		if (document.scrollingElement instanceof HTMLElement) return document.scrollingElement
		return document.documentElement
	}

	function findScrollContainer(node: HTMLElement): HTMLElement | null {
		let current: HTMLElement | null = node
		while (current) {
			const style = getComputedStyle(current)
			const overflowY = style.overflowY
			const canScroll =
				overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay'
			if (canScroll) return current
			current = current.parentElement
		}
		return null
	}

	function maybeLoadMoreFromPage(target: HTMLElement): void {
		if (!useInfiniteScroll || !hasMore || loadingMore || loadMoreInFlight) return
		const remaining = target.scrollHeight - target.scrollTop - target.clientHeight
		const threshold = Math.min(
			PAGE_LOAD_MORE_THRESHOLD,
			Math.max(160, target.clientHeight * 0.75)
		)
		if (remaining > threshold) return

		const result = requestLoadMoreResources()
		if (!result) return
		const request = Promise.resolve(result)
		loadMoreInFlight = request
		void request
			.catch(() => {})
			.finally(() => {
				if (loadMoreInFlight === request) loadMoreInFlight = null
			})
	}

	/** Add current sharing metadata to a displayed resource. */
	function resourceWithSharing(resource: ResourceItem): ResourceItem {
		const shared = isSharedResource(resource)
		const ownerId = resourceOwnerId(resource)
		const authorLabel = shared ? session.authorLabel(ownerId) : null
		const accessType = accessResourceType(resource.type)
		const accessLevel = accessType
			? resourceAccess.level(accessType, resource.id, ownerId)
			: null
		if (
			resource.meta?.shared === shared &&
			resource.meta?.author_label === authorLabel &&
			resource.meta?.access_level === accessLevel
		) {
			return resource
		}
		return {
			...resource,
			meta: {
				...(resource.meta ?? {}),
				shared,
				author_label: authorLabel,
				access_level: accessLevel,
			},
		}
	}

	function selectedProjectIds(resource: ResourceItem): string[] {
		if (getItemProjectIds) return getItemProjectIds(resource)
		const projectIds = resource.meta?.project_ids
		return Array.isArray(projectIds)
			? projectIds.filter((id): id is string => typeof id === 'string')
			: []
	}

	function chunkResourceRows(items: ResourceItem[]): ResourceVirtualRow[] {
		const rows: ResourceVirtualRow[] = []
		const chunkSize = layout === 'grid' ? virtualGridColumns : 1
		for (let index = 0; index < items.length; index += chunkSize) {
			const chunk = items.slice(index, index + chunkSize)
			const firstResource = chunk[0]
			if (!firstResource) continue
			rows.push({
				kind: 'resources',
				id: `${layout}:${virtualGridColumns}:${firstResource.id}`,
				items: chunk,
			})
		}
		return rows
	}

	function buildVirtualRows(): ResourceVirtualRow[] {
		const rows: ResourceVirtualRow[] = []
		if (showSharedSections) {
			rows.push({
				kind: 'section',
				id: 'section:owned',
				label: ownedSectionLabel,
				count: displayedOwnedSectionCount,
				open: ownedSectionOpen,
				target: 'owned',
			})
			if (ownedSectionOpen) {
				if (ownedResources.length > 0) rows.push(...chunkResourceRows(ownedResources))
				else rows.push({ kind: 'empty', id: 'empty:owned', message: ownedEmptyMessage })
			}

			rows.push({
				kind: 'section',
				id: 'section:shared',
				label: sharedSectionLabel,
				count: displayedSharedSectionCount,
				open: effectiveSharedSectionOpen,
				target: 'shared',
			})
			if (effectiveSharedSectionOpen) {
				if (sharedResources.length > 0) rows.push(...chunkResourceRows(sharedResources))
				else rows.push({ kind: 'empty', id: 'empty:shared', message: sharedEmptyMessage })
			}
		} else {
			rows.push(...chunkResourceRows(paginated))
		}

		if (useInfiniteScroll && loadingMore) rows.push({ kind: 'loading', id: 'loading' })
		return rows
	}

	function toggleSection(target: 'owned' | 'shared'): void {
		if (target === 'owned') {
			ownedSectionOpen = !ownedSectionOpen
			return
		}
		sharedSectionOpen = !sharedSectionOpen
	}

	function requestLoadMoreResources(): void | Promise<void> {
		if (!useInfiniteScroll || !hasMore || loadingMore || loadMoreInFlight) return
		return onLoadMore?.()
	}
</script>

{#snippet resourceCard(resource: ResourceItem)}
	{@const displayResource = resourceWithSharing(resource)}
	{#if resource.type === 'thread'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<ChatWidget
				resource={displayResource}
				layout={concreteLayout}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{:else if resource.type === 'note'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<NoteWidget
				resource={displayResource}
				layout={concreteLayout}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{:else if resource.type === 'reminder' || resource.type === 'reminder_list'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<RemindersListWidget
				resource={displayResource}
				layout={concreteLayout}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{:else if resource.type === 'project'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<ProjectWidget
				resource={displayResource}
				layout={concreteLayout}
				onEdit={onItemEdit ? () => onItemEdit(resource) : undefined}
				onShare={onItemShare ? () => onItemShare(resource) : undefined}
				onDelete={onItemDelete ? () => onItemDelete(resource) : undefined}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{:else if resource.type === 'file'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<FileWidget
				resource={displayResource}
				layout={concreteLayout}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{:else if resource.type === 'calendar_event' || resource.type === 'calendar'}
		{#if effectiveLayout === 'pill'}
			<ResourceWidget
				resource={displayResource}
				layout="pill"
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{:else}
			<CalendarWidget
				resource={displayResource}
				layout={concreteLayout}
				onclick={onItemClick ? () => onItemClick(resource) : undefined}
			/>
		{/if}
	{/if}
{/snippet}

{#snippet actionWrappedResourceCard(resource: ResourceItem)}
	{@const displayResource = resourceWithSharing(resource)}
	<div class="group/resource relative min-w-0">
		{@render resourceCard(resource)}
		{#if hasGenericActions && resource.type !== 'project'}
			<ResourceActionMenu
				resource={displayResource}
				layout={concreteLayout}
				{projectOptions}
				selectedProjectIds={selectedProjectIds(resource)}
				onProperties={onItemEdit ? () => onItemEdit(resource) : undefined}
				onShare={onItemShare ? () => onItemShare(resource) : undefined}
				onDelete={onItemDelete ? () => onItemDelete(resource) : undefined}
				onRemoveFromProject={onItemRemoveFromProject
					? () => onItemRemoveFromProject(resource)
					: undefined}
				onProjectToggle={onItemProjectToggle
					? (targetProjectId, selected) =>
							onItemProjectToggle(resource, targetProjectId, selected)
					: undefined}
			/>
		{/if}
	</div>
{/snippet}

{#snippet virtualResourceRow(row: ResourceVirtualRow)}
	{#if row.kind === 'section'}
		{@render sectionHeader(row.label, row.count, row.open, () => toggleSection(row.target))}
	{:else if row.kind === 'empty'}
		<div class="pb-4">
			<EmptyState label={row.message} class="min-h-56" />
		</div>
	{:else if row.kind === 'loading'}
		<LoadingMoreIndicator className="py-6" label="loading more resources" />
	{:else if layout === 'grid'}
		<div class="grid gap-4 pb-4" style={virtualGridRowStyle}>
			{#each row.items as resource (resource.id)}
				{@render actionWrappedResourceCard(resource)}
			{/each}
		</div>
	{:else}
		<div class="flex flex-col gap-2 pb-2">
			{#each row.items as resource (resource.id)}
				{@render actionWrappedResourceCard(resource)}
			{/each}
		</div>
	{/if}
{/snippet}

{#snippet sectionHeader(label: string, count: number, open: boolean, onToggle: () => void)}
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground/90 flex w-full cursor-pointer items-center gap-1.5 bg-transparent px-1 py-2 text-xs font-semibold tracking-wide uppercase transition-colors duration-150"
		onclick={onToggle}
		aria-expanded={open}
	>
		<ChevronDown class="h-3 w-3 transition-transform duration-200 {open ? '' : '-rotate-90'}" />
		<span>{label}</span>
		<span class="text-foreground/50 font-normal">({count})</span>
	</button>
{/snippet}

<div bind:this={rootEl} class="relative flex flex-col gap-4 {className}">
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
		<div class={layout === 'grid' ? resourceGridClass : 'flex flex-col gap-2'}>
			{#each [0, 1, 2, 3, 4, 5] as i (i)}
				<div
					class="liquid-glass liquid-glass--frosted animate-pulse overflow-hidden {layout ===
					'grid'
						? 'h-80 rounded-2xl'
						: effectiveLayout === 'pill'
							? 'rounded-pill h-12'
							: 'h-16 rounded-2xl'}"
				></div>
			{/each}
		</div>
	{:else if paginated.length === 0 && !showSharedSections}
		<EmptyState label={emptyMessage} class="min-h-[45vh] flex-1 overflow-hidden py-16" />
	{:else}
		<div bind:this={virtualCollectionEl} class="relative w-full">
			<div class="flex w-full flex-col">
				{#each virtualRows as row (row.id)}
					<div data-resource-view-row={row.kind} data-resource-view-row-id={row.id}>
						{@render virtualResourceRow(row)}
					</div>
				{/each}
			</div>
		</div>
	{/if}

	{#if showScrollTopButton}
		<FloatingScrollTopButton
			target={pageScrollTarget}
			class="pointer-events-none fixed z-20 flex justify-center"
			style="left: var(--island-left, 0px); right: 0; bottom: {scrollTopButtonBottom};"
		/>
	{/if}

	{#if !useInfiniteScroll && showPagination && totalPages > 1}
		<div class="flex items-center justify-center gap-3 pt-2">
			<button
				type="button"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/60 hover:bg-foreground/10 cursor-pointer border px-3 py-1.5 text-xs transition-colors duration-150 disabled:cursor-default disabled:opacity-30"
				onclick={prevPage}
				disabled={currentPage === 0}
			>
				previous
			</button>
			<span class="text-foreground/40 text-xs">
				{currentPage + 1} / {totalPages}
			</span>
			<button
				type="button"
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/60 hover:bg-foreground/10 cursor-pointer border px-3 py-1.5 text-xs transition-colors duration-150 disabled:cursor-default disabled:opacity-30"
				onclick={nextPage}
				disabled={currentPage >= totalPages - 1}
			>
				next
			</button>
		</div>
	{/if}
</div>

<style>
	.resource-grid {
		grid-template-columns: repeat(auto-fill, minmax(min(100%, 21.25rem), 1fr));
	}

	@media (min-width: 420px) and (max-width: 639px) {
		.resource-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
</style>
