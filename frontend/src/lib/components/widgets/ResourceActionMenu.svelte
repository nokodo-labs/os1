<script lang="ts">
	/**
	 * overflow menu for a resource card. the whole card opens it on right-click
	 * and on touch hold: mark the card `data-row` and the menu finds it from its
	 * own trigger (see `attachments/contextmenu`).
	 */

	import { contextmenu, type ContextMenuAnchor } from '$lib/attachments/contextmenu'
	import { THREAD_ORIGINATED_TOGGLE } from '$lib/chat/threadActions'
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import InfoCircle from '$lib/components/icons/InfoCircle.svelte'
	import Minus from '$lib/components/icons/Minus.svelte'
	import Share from '$lib/components/icons/Share.svelte'
	import { MenuItem, MenuSeparator, PopupMenu } from '$lib/components/primitives'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { device } from '$lib/stores/device.svelte'
	import {
		canDeleteAccessLevel,
		canEditAccessLevel,
		readAccessLevel,
		resourceAccess,
		type AccessControlledResourceType,
	} from '$lib/stores/resourceAccess.svelte'
	import type { ResourceProjectOption } from './ResourceProjectsMenu.svelte'
	import ResourceProjectsMenu from './ResourceProjectsMenu.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		projectOptions?: ResourceProjectOption[]
		selectedProjectIds?: string[]
		onProperties?: () => void
		onShare?: () => void
		onDelete?: (deleteOriginatedResources: boolean) => Promise<boolean> | boolean | void
		onRemoveFromProject?: () => Promise<void> | void
		onProjectToggle?: (projectId: string, selected: boolean) => Promise<void> | void
	}

	let {
		resource,
		layout = 'grid',
		projectOptions = [],
		selectedProjectIds = [],
		onProperties,
		onShare,
		onDelete,
		onRemoveFromProject,
		onProjectToggle,
	}: Props = $props()

	let menuOpen = $state(false)
	let menuButtonEl = $state<HTMLButtonElement | null>(null)
	let anchorPoint = $state<ContextMenuAnchor | null>(null)

	const ownerId = $derived(
		typeof resource.meta?.owner_id === 'string' ? resource.meta.owner_id : null
	)
	/** return the access-controlled container type for a menu resource. */
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
			case 'message':
				return null
		}
	}
	const accessType = $derived(accessResourceType(resource.type))
	const accessLevel = $derived(
		(accessType ? resourceAccess.level(accessType, resource.id, ownerId) : null) ??
			readAccessLevel(resource.meta?.access_level)
	)
	const canEdit = $derived(canEditAccessLevel(accessLevel))
	const canDelete = $derived(canDeleteAccessLevel(accessLevel))
	const canManageProjects = $derived(Boolean(onProjectToggle && canEdit))
	const projectVisual = resourceVisual('project')
	const ProjectIcon = projectVisual.icon
	const projectAccentStyle = resourceAccentStyle('project')
	const hasActions = $derived(
		Boolean(
			(onProperties && canEdit) ||
			onShare ||
			(onDelete && canDelete) ||
			(onRemoveFromProject && canEdit) ||
			canManageProjects
		)
	)
	const visibilityClass = $derived(
		device.isTouch || !device.hasHover
			? 'opacity-100'
			: 'opacity-0 group-hover/resource:opacity-100'
	)
	const buttonPositionClass = $derived(
		layout === 'list' ? 'top-1/2 right-4 -translate-y-1/2' : 'top-[10.25rem] right-6'
	)

	function closeMenus(): void {
		menuOpen = false
	}

	function toggleMenu(event: MouseEvent): void {
		event.preventDefault()
		event.stopPropagation()
		anchorPoint = null
		menuOpen = !menuOpen
	}

	$effect(() => {
		const row = menuButtonEl?.closest('[data-row]')
		if (!(row instanceof HTMLElement)) return
		return contextmenu({
			onOpen: (anchor) => {
				anchorPoint = anchor
				menuOpen = true
			},
		})(row)
	})

	function runAction(action: (() => void | Promise<void>) | undefined): void {
		if (!action) return
		closeMenus()
		void action()
	}
</script>

{#if hasActions}
	<button
		type="button"
		bind:this={menuButtonEl}
		class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground absolute z-20 flex size-9 cursor-pointer items-center justify-center rounded-full border-none bg-transparent transition-all duration-150 hover:scale-[1.04] active:scale-[0.97] {buttonPositionClass} {visibilityClass}"
		onpointerdown={(event) => event.stopPropagation()}
		onclick={toggleMenu}
		aria-label="resource options"
		aria-haspopup="menu"
		aria-expanded={menuOpen}
	>
		<EllipsisHorizontal class="size-5" />
	</button>

	<PopupMenu
		open={menuOpen}
		anchorEl={menuButtonEl}
		{anchorPoint}
		onClose={closeMenus}
		class="min-w-52"
	>
		{#if onProperties && canEdit}
			<MenuItem icon={InfoCircle} onclick={() => runAction(onProperties)}>properties</MenuItem
			>
		{/if}
		{#if onShare}
			<MenuItem icon={Share} onclick={() => runAction(onShare)}>share</MenuItem>
		{/if}
		{#if onRemoveFromProject && canEdit}
			<MenuItem onclick={() => runAction(onRemoveFromProject)}>
				{#snippet iconSnippet()}
					<span
						class="relative flex size-full items-center justify-center"
						style={projectAccentStyle}
					>
						<ProjectIcon class="size-full text-(--accent-primary)" />
						<Minus
							class="absolute -right-1 -bottom-0.5 size-3.5 text-red-400"
							strokeWidth="2.6"
						/>
					</span>
				{/snippet}
				remove from project
			</MenuItem>
		{/if}
		{#if canManageProjects}
			<ResourceProjectsMenu {projectOptions} {selectedProjectIds} {onProjectToggle} />
		{/if}
		{#if onDelete && canDelete}
			<MenuSeparator />
			<DeleteButton
				confirm={true}
				stopPropagation={true}
				onTrigger={closeMenus}
				modalText={{
					title: `delete ${resource.title || 'resource'}?`,
					description: resource.title,
				}}
				modalToggle={resource.type === 'thread' ? THREAD_ORIGINATED_TOGGLE : undefined}
				{onDelete}
			/>
		{/if}
	</PopupMenu>
{/if}
