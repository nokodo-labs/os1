<script lang="ts">
	import { resolve } from '$app/paths'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import User from '$lib/components/icons/User.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import {
		projectResourceTypes,
		resourceAccentStyle,
		resourceVisual,
		type ResourceVisualType,
	} from '$lib/resources/resourceVisuals'
	import { device } from '$lib/stores/device.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		readAccessLevel,
		resourceAccess,
	} from '$lib/stores/resourceAccess.svelte'
	import { metadataLine } from '$lib/utils/resourceAuthors'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onEdit?: () => void
		onShare?: () => void
		onDelete?: () => Promise<boolean> | boolean | void
		onclick?: () => void
	}

	let {
		resource,
		layout = 'grid',
		class: className = '',
		onEdit,
		onShare,
		onDelete,
		onclick,
	}: Props = $props()

	const countsLoaded = $derived(resource.meta?.counts_loaded === true)
	const threadCount = $derived(
		countsLoaded ? ((resource.meta?.thread_count as number | undefined) ?? 0) : 0
	)
	const noteCount = $derived(
		countsLoaded ? ((resource.meta?.note_count as number | undefined) ?? 0) : 0
	)
	const fileCount = $derived(
		countsLoaded ? ((resource.meta?.file_count as number | undefined) ?? 0) : 0
	)
	const reminderListCount = $derived(
		countsLoaded ? ((resource.meta?.reminder_list_count as number | undefined) ?? 0) : 0
	)
	const calendarCount = $derived(
		countsLoaded ? ((resource.meta?.calendar_count as number | undefined) ?? 0) : 0
	)
	const fallbackResourceCount = $derived(
		threadCount + noteCount + fileCount + reminderListCount + calendarCount
	)
	const resourceCount = $derived(
		countsLoaded
			? ((resource.meta?.resource_count as number | undefined) ?? fallbackResourceCount)
			: 0
	)
	const memberCount = $derived((resource.meta?.member_count as number) ?? 0)
	const isShared = $derived(Boolean(resource.meta?.shared))
	const ownerId = $derived(
		typeof resource.meta?.owner_id === 'string' ? resource.meta.owner_id : null
	)
	const authorLabel = $derived((resource.meta?.author_label as string | null) ?? null)
	const showAuthor = $derived(Boolean(isShared && authorLabel))
	const accessLevel = $derived(
		resourceAccess.level('project', resource.id, ownerId) ??
			readAccessLevel(resource.meta?.access_level)
	)
	const canEditProject = $derived(canEditAccessLevel(accessLevel))
	const canDeleteProject = $derived(canDeleteAccessLevel(accessLevel))
	const hasActions = $derived(
		Boolean(onShare || (onEdit && canEditProject) || (onDelete && canDeleteProject))
	)

	let menuOpen = $state(false)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let showDeleteConfirm = $state(false)
	const projectVisual = resourceVisual('project')
	const ProjectIcon = projectVisual.icon
	const projectAccentStyle = resourceAccentStyle('project')

	const stats = $derived.by(() => {
		if (!countsLoaded) return 'resources'
		if (resourceCount > 0) {
			return `${resourceCount} resource${resourceCount !== 1 ? 's' : ''}`
		}
		return 'empty project'
	})
	const countItems = $derived.by(() => {
		if (!countsLoaded) return []
		return projectResourceTypes
			.map((type) => ({ type, count: countForType(type) }))
			.filter((item) => item.count > 0)
	})
	const previewCaption = $derived(
		showAuthor ? 'shared project' : memberCount > 0 ? 'team workspace' : 'project workspace'
	)
	const previewTiles = $derived.by(() => {
		const tiles: ResourceVisualType[] = []
		for (const item of countItems) {
			const tileCount = Math.min(item.count, 4)
			for (let i = 0; i < tileCount; i += 1) tiles.push(item.type)
		}
		return tiles.slice(0, 12)
	})
	const projectMeta = $derived(metadataLine(stats))
	const actionVisibilityClass = $derived(
		device.isTouch || !device.hasHover ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
	)

	function handleMenuClick(event: MouseEvent) {
		event.preventDefault()
		event.stopPropagation()
		menuOpen = !menuOpen
	}

	function handleClick(event: MouseEvent): void {
		if (!onclick) return
		event.preventDefault()
		onclick()
	}

	function countForType(type: ResourceVisualType): number {
		switch (type) {
			case 'thread':
				return threadCount
			case 'note':
				return noteCount
			case 'file':
				return fileCount
			case 'reminder_list':
				return reminderListCount
			case 'calendar':
				return calendarCount
			default:
				return 0
		}
	}
</script>

<a
	href={resolve(`/projects/${resource.id}`)}
	onclick={handleClick}
	class="group liquid-glass liquid-glass--frosted relative block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone={projectVisual.tone}
			label={projectVisual.label}
			caption={previewCaption}
			showFallback={countsLoaded && resourceCount === 0}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<ProjectIcon variant="solid" class="size-6" />
			{/snippet}
			{#if previewTiles.length > 0}
				<div class="flex h-full w-full items-center justify-center p-4">
					<div class="grid grid-cols-4 gap-2">
						{#each previewTiles as type, index (`${type}-${index}`)}
							{@const visual = resourceVisual(type)}
							{@const Icon = visual.icon}
							<div
								class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_18%,transparent)] text-(--accent-primary) shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)]"
								style={resourceAccentStyle(type)}
								aria-label={visual.label}
							>
								<Icon variant="solid" class="size-5" />
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={projectAccentStyle}
			>
				<ProjectIcon variant="solid" class="size-5" />
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">project</span>
				{#if showAuthor}
					<span
						class="text-foreground/40 flex min-w-0 items-center gap-1 truncate text-[11px]"
					>
						<User class="h-3 w-3 shrink-0" />
						<span class="min-w-0 truncate">{authorLabel}</span>
					</span>
				{:else if memberCount > 0}
					<span class="text-foreground/40 truncate text-[11px]"
						>{memberCount} member{memberCount !== 1 ? 's' : ''}</span
					>
				{/if}
			</div>
			{#if hasActions}
				<button
					type="button"
					bind:this={menuButtonEl}
					class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground/90 ml-auto flex size-9 cursor-pointer items-center justify-center rounded-xl border-none bg-transparent transition-all duration-150 {actionVisibilityClass}"
					onclick={handleMenuClick}
					aria-label="project options"
					aria-haspopup="menu"
					aria-expanded={menuOpen}
				>
					<EllipsisHorizontal class="size-5" />
				</button>
				<PopupMenu
					open={menuOpen}
					anchorEl={menuButtonEl}
					onClose={() => (menuOpen = false)}
				>
					{#if onEdit && canEditProject}
						<MenuItem
							onclick={() => {
								menuOpen = false
								onEdit()
							}}
						>
							{#snippet icon()}<InfoCircle
									variant="solid"
									class="size-full"
								/>{/snippet}
							project properties
						</MenuItem>
					{/if}
					{#if onShare}
						<MenuItem
							onclick={() => {
								menuOpen = false
								onShare()
							}}
						>
							{#snippet icon()}<Share class="size-full" />{/snippet}
							share
						</MenuItem>
					{/if}
					{#if onDelete && canDeleteProject}
						<MenuItem
							destructive
							onclick={(e: MouseEvent) => {
								e.preventDefault()
								e.stopPropagation()
								menuOpen = false
								showDeleteConfirm = true
							}}
						>
							{#snippet icon()}<Trash class="size-full" />{/snippet}
							delete
						</MenuItem>
					{/if}
				</PopupMenu>
			{/if}
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled project'}
		</h3>
		{#if resource.subtitle}
			<p class="text-foreground/70 mb-2 line-clamp-2 text-sm leading-relaxed">
				{resource.subtitle}
			</p>
		{/if}
		{#if countItems.length > 0}
			<div class="mb-2 flex min-w-0 flex-wrap gap-1.5">
				{#each countItems as item (item.type)}
					{@const visual = resourceVisual(item.type)}
					{@const Icon = visual.icon}
					<span
						class="flex min-w-0 items-center gap-1.5 px-0.5 py-0.5 text-(--accent-primary)"
						style={resourceAccentStyle(item.type)}
						title={visual.pluralLabel}
					>
						<Icon variant="solid" class="size-3.5 shrink-0" />
						<span class="text-xs font-semibold tabular-nums">{item.count}</span>
					</span>
				{/each}
			</div>
		{:else}
			<p class="text-foreground/55 mb-1 min-w-0 truncate text-sm">{projectMeta}</p>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="mt-auto text-xs text-foreground/45"
		/>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
			style={projectAccentStyle}
		>
			<ProjectIcon variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled project'}
			</h3>
			<p class="text-foreground/65 truncate text-sm">{projectMeta}</p>
			{#if showAuthor}
				<p
					class="text-foreground/45 mt-0.5 flex min-w-0 items-center gap-1.5 truncate text-xs"
				>
					<User class="h-3 w-3 shrink-0" />
					<span class="min-w-0 truncate">{authorLabel}</span>
				</p>
			{/if}
		</div>
		{#if memberCount > 0}
			<span class="text-foreground/45 shrink-0 text-xs">{memberCount} members</span>
		{/if}
		{#if hasActions}
			<button
				type="button"
				bind:this={menuButtonEl}
				class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground/90 flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-xl border-none bg-transparent transition-all duration-150 {actionVisibilityClass}"
				onclick={handleMenuClick}
				aria-label="project options"
				aria-haspopup="menu"
				aria-expanded={menuOpen}
			>
				<EllipsisHorizontal class="size-5" />
			</button>
			<PopupMenu open={menuOpen} anchorEl={menuButtonEl} onClose={() => (menuOpen = false)}>
				{#if onEdit && canEditProject}
					<MenuItem
						onclick={() => {
							menuOpen = false
							onEdit()
						}}
					>
						{#snippet icon()}<InfoCircle variant="solid" class="size-full" />{/snippet}
						project properties
					</MenuItem>
				{/if}
				{#if onShare}
					<MenuItem
						onclick={() => {
							menuOpen = false
							onShare()
						}}
					>
						{#snippet icon()}<Share class="size-full" />{/snippet}
						share
					</MenuItem>
				{/if}
				{#if onDelete && canDeleteProject}
					<MenuItem
						destructive
						onclick={(e: MouseEvent) => {
							e.preventDefault()
							e.stopPropagation()
							menuOpen = false
							showDeleteConfirm = true
						}}
					>
						{#snippet icon()}<Trash class="size-full" />{/snippet}
						delete
					</MenuItem>
				{/if}
			</PopupMenu>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>

{#if onDelete && canDeleteProject}
	<DeleteButton
		showTrigger={false}
		bind:open={showDeleteConfirm}
		{onDelete}
		modalText={{
			title: 'delete project?',
			description: 'this will remove the project but not its resources.',
		}}
	/>
{/if}
