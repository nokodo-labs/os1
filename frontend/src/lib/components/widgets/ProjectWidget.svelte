<script lang="ts">
	import { resolve } from '$app/paths'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import FinderFolder from '$lib/components/icons/FinderFolder.svelte'
	import PencilSquare from '$lib/components/icons/PencilSquare.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onEdit?: () => void
		onDelete?: () => Promise<boolean> | boolean | void
	}

	let { resource, layout = 'grid', class: className = '', onEdit, onDelete }: Props = $props()

	const threadCount = $derived((resource.meta?.thread_count as number) ?? 0)
	const noteCount = $derived((resource.meta?.note_count as number) ?? 0)
	const fileCount = $derived((resource.meta?.file_count as number) ?? 0)
	const memberCount = $derived((resource.meta?.member_count as number) ?? 0)
	const hasActions = $derived(!!onEdit || !!onDelete)

	let menuOpen = $state(false)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let showDeleteConfirm = $state(false)

	const stats = $derived.by(() => {
		const parts: string[] = []
		if (threadCount > 0) parts.push(`${threadCount} chat${threadCount !== 1 ? 's' : ''}`)
		if (noteCount > 0) parts.push(`${noteCount} note${noteCount !== 1 ? 's' : ''}`)
		if (fileCount > 0) parts.push(`${fileCount} file${fileCount !== 1 ? 's' : ''}`)
		return parts.length > 0 ? parts.join(' - ') : 'empty project'
	})

	function handleMenuClick(event: MouseEvent) {
		event.preventDefault()
		event.stopPropagation()
		menuOpen = !menuOpen
	}
</script>

<a
	href={resolve(`/projects/${resource.id}`)}
	class="group liquid-glass liquid-glass--frosted relative block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<div class="mb-4 flex items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-yellow-400/15 text-yellow-400"
			>
				<FinderFolder class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">project</span>
				{#if memberCount > 0}
					<span class="text-foreground/40 text-[11px]"
						>{memberCount} member{memberCount !== 1 ? 's' : ''}</span
					>
				{/if}
			</div>
			{#if hasActions}
				<button
					type="button"
					bind:this={menuButtonEl}
					class="text-foreground/40 hover:text-foreground/80 ml-auto flex size-7 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent opacity-0 transition-all duration-150 group-hover:opacity-100"
					onclick={handleMenuClick}
					aria-label="project options"
					aria-haspopup="menu"
					aria-expanded={menuOpen}
				>
					<EllipsisHorizontal class="size-4" />
				</button>
				<PopupMenu
					open={menuOpen}
					anchorEl={menuButtonEl}
					onClose={() => (menuOpen = false)}
				>
					{#if onEdit}
						<MenuItem
							onclick={() => {
								menuOpen = false
								onEdit()
							}}
						>
							{#snippet icon()}<PencilSquare class="size-4" />{/snippet}
							edit project
						</MenuItem>
					{/if}
					{#if onDelete}
						<button
							type="button"
							class="group/del rounded-pill text-foreground/80 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
							onclick={(e: MouseEvent) => {
								e.preventDefault()
								e.stopPropagation()
								menuOpen = false
								showDeleteConfirm = true
							}}
						>
							<Trash
								class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover/del:text-red-300"
							/>
							<span class="ml-2">delete</span>
						</button>
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
		<p class="text-foreground/55 mb-1 text-sm">{stats}</p>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="mt-auto text-xs text-foreground/45"
		/>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-yellow-400/15 text-yellow-400"
		>
			<FinderFolder class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled project'}
			</h3>
			<p class="text-foreground/65 truncate text-sm">{stats}</p>
		</div>
		{#if memberCount > 0}
			<span class="text-foreground/45 shrink-0 text-xs">{memberCount} members</span>
		{/if}
		{#if hasActions}
			<button
				type="button"
				bind:this={menuButtonEl}
				class="text-foreground/40 hover:text-foreground/80 flex size-7 shrink-0 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent opacity-0 transition-all duration-150 group-hover:opacity-100"
				onclick={handleMenuClick}
				aria-label="project options"
				aria-haspopup="menu"
				aria-expanded={menuOpen}
			>
				<EllipsisHorizontal class="size-4" />
			</button>
			<PopupMenu open={menuOpen} anchorEl={menuButtonEl} onClose={() => (menuOpen = false)}>
				{#if onEdit}
					<MenuItem
						onclick={() => {
							menuOpen = false
							onEdit()
						}}
					>
						{#snippet icon()}<PencilSquare class="size-4" />{/snippet}
						edit project
					</MenuItem>
				{/if}
				{#if onDelete}
					<button
						type="button"
						class="group/del rounded-pill text-foreground/80 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
						onclick={(e: MouseEvent) => {
							e.preventDefault()
							e.stopPropagation()
							menuOpen = false
							showDeleteConfirm = true
						}}
					>
						<Trash
							class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover/del:text-red-300"
						/>
						<span class="ml-2">delete</span>
					</button>
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

{#if onDelete}
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
