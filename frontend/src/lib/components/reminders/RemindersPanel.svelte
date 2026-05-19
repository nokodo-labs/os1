<script lang="ts">
	import { browser } from '$app/environment'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import {
		reminders,
		type ReminderUpdate,
		type ReminderWithSubtasks,
	} from '$lib/stores/reminders.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { onDestroy, tick, untrack } from 'svelte'
	import { SvelteMap } from 'svelte/reactivity'
	import ReminderRow from './ReminderRow.svelte'

	interface Props {
		listId: string | null
		showListTitle?: boolean
	}

	let { listId, showListTitle = false }: Props = $props()

	// state

	let isLoading = $state(true)
	let showCompleted = $state(false)
	let isAddingReminder = $state(false)
	let isAddingExpanded = $state(false)
	let expandedReminderId = $state<string | null>(null)
	let loadToken = 0

	/** animation state for reminders transitioning between pending/completed */
	interface TransitionEntry {
		direction: 'to-completed' | 'to-pending'
		reminder: ReminderWithSubtasks
	}
	type ReminderSection = 'pending' | 'completed'
	type DropPosition = 'before' | 'after' | 'child'
	interface ReminderTreeItem {
		reminder: ReminderWithSubtasks
		depth: number
		parentId: string | null
	}
	const transitions = new SvelteMap<string, TransitionEntry>()

	/** animation state for reminders entering the list */
	interface IncomingEntry {
		delayMs: number
		iconMorph?: 'plus-to-circle' | null
	}
	const incoming = new SvelteMap<string, IncomingEntry>()

	const MOTION_MS = 420
	let draggingReminderId = $state<string | null>(null)
	let dropReminderId = $state<string | null>(null)
	let dropPosition = $state<DropPosition | null>(null)
	let pointerDragCleanup: (() => void) | null = null

	// derived

	const remindersList = $derived(reminders.getReminders(listId))
	const reminderTreeItems = $derived(flattenReminderItems(remindersList))
	const completedCount = $derived(
		reminderTreeItems.filter((item) => item.reminder.status === 'completed').length
	)

	/** pending reminders - exclude items currently transitioning out */
	const pendingReminderItems = $derived(
		reminderTreeItems.filter((item) => belongsToSection(item.reminder, 'pending'))
	)

	/** completed reminders - exclude items currently transitioning out */
	const completedReminderItems = $derived(
		reminderTreeItems.filter((item) => belongsToSection(item.reminder, 'completed'))
	)

	const availableLists = $derived(reminders.lists)
	const activeList = $derived(listId ? reminders.getListById(listId) : reminders.defaultList)
	const activeListAccessLevel = $derived(
		activeList
			? resourceAccess.level('reminder_list', activeList.id, activeList.owner_id)
			: null
	)
	const canEditActiveList = $derived(canEditAccessLevel(activeListAccessLevel))

	// helpers

	function sortByPosition(items: ReminderWithSubtasks[]): ReminderWithSubtasks[] {
		return [...items].sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
	}

	function flattenReminderItems(
		items: ReminderWithSubtasks[],
		depth = 0,
		parentId: string | null = null
	): ReminderTreeItem[] {
		const flattened: ReminderTreeItem[] = []
		for (const reminder of sortByPosition(items)) {
			flattened.push({ reminder, depth, parentId })
			const subtasks = reminder.subtasks ?? []
			if (subtasks.length > 0) {
				flattened.push(...flattenReminderItems(subtasks, depth + 1, reminder.id))
			}
		}
		return flattened
	}

	function belongsToSection(reminder: ReminderWithSubtasks, section: ReminderSection): boolean {
		const transition = transitions.get(reminder.id)
		if (section === 'pending') {
			if (transition?.direction === 'to-completed') return true
			return reminder.status === 'pending' && !transition
		}
		if (transition?.direction === 'to-pending') return true
		return reminder.status === 'completed' && !transition
	}

	function itemParentId(item: ReminderTreeItem): string | null {
		return item.reminder.parent_id ?? item.parentId
	}

	function findTreeItem(reminderId: string | null): ReminderTreeItem | null {
		if (!reminderId) return null
		return reminderTreeItems.find((item) => item.reminder.id === reminderId) ?? null
	}

	function isDescendantOf(reminderId: string, ancestorId: string): boolean {
		let current = findTreeItem(reminderId)
		while (current) {
			const parentId = itemParentId(current)
			if (!parentId) return false
			if (parentId === ancestorId) return true
			current = findTreeItem(parentId)
		}
		return false
	}

	function siblingsForParent(parentId: string | null): ReminderWithSubtasks[] {
		return reminderTreeItems
			.filter((item) => itemParentId(item) === parentId)
			.map((item) => item.reminder)
	}

	function cloneReminderTree(items: ReminderWithSubtasks[]): ReminderWithSubtasks[] {
		return items.map((item) => ({
			...item,
			subtasks: cloneReminderTree(item.subtasks ?? []),
		}))
	}

	function removeReminderFromTree(
		items: ReminderWithSubtasks[],
		sourceId: string
	): { items: ReminderWithSubtasks[]; removed: ReminderWithSubtasks | null } {
		const next: ReminderWithSubtasks[] = []
		let removed: ReminderWithSubtasks | null = null

		for (const item of items) {
			if (item.id === sourceId) {
				removed = item
				continue
			}

			const childResult = removeReminderFromTree(item.subtasks ?? [], sourceId)
			if (childResult.removed) removed = childResult.removed
			next.push({ ...item, subtasks: childResult.items })
		}

		return { items: next, removed }
	}

	function findOptimisticSiblings(
		items: ReminderWithSubtasks[],
		parentId: string | null
	): ReminderWithSubtasks[] | null {
		if (parentId === null) return items
		for (const item of items) {
			if (item.id === parentId) {
				item.subtasks = item.subtasks ?? []
				return item.subtasks
			}
			const childSiblings = findOptimisticSiblings(item.subtasks ?? [], parentId)
			if (childSiblings) return childSiblings
		}
		return null
	}

	function buildOptimisticReorder(
		sourceId: string,
		nextParentId: string | null,
		insertIndex: number
	): ReminderWithSubtasks[] | null {
		const snapshot = cloneReminderTree(reminders.getReminders(listId))
		const { items, removed } = removeReminderFromTree(snapshot, sourceId)
		if (!removed) return null

		const siblings = findOptimisticSiblings(items, nextParentId)
		if (!siblings) return null

		siblings.splice(insertIndex, 0, { ...removed, parent_id: nextParentId })
		for (let index = 0; index < siblings.length; index++) {
			siblings[index] = {
				...siblings[index],
				parent_id: nextParentId,
				position: index,
			}
		}

		return items
	}

	function computeDropPositionFromPoint(
		clientX: number,
		clientY: number,
		element: HTMLElement,
		target: ReminderTreeItem
	): DropPosition {
		const rect = element.getBoundingClientRect()
		const y = (clientY - rect.top) / Math.max(rect.height, 1)
		if (y < 0.24) return 'before'
		if (y > 0.76) return 'after'
		const x = clientX - rect.left
		const childThreshold = 64 + target.depth * 20
		return x > childThreshold ? 'child' : 'after'
	}

	function computeDropPosition(event: DragEvent, target: ReminderTreeItem): DropPosition {
		return computeDropPositionFromPoint(
			event.clientX,
			event.clientY,
			event.currentTarget as HTMLElement,
			target
		)
	}

	function setDropTarget(target: ReminderTreeItem, position: DropPosition): boolean {
		if (
			!draggingReminderId ||
			draggingReminderId === target.reminder.id ||
			isDescendantOf(target.reminder.id, draggingReminderId) ||
			isNoopDrop(draggingReminderId, target, position)
		) {
			dropReminderId = null
			dropPosition = null
			return false
		}

		dropReminderId = target.reminder.id
		dropPosition = position
		return true
	}

	function clearDragState(): void {
		pointerDragCleanup?.()
		pointerDragCleanup = null
		draggingReminderId = null
		dropReminderId = null
		dropPosition = null
	}

	function getDropTarget(reminderId: string): DropPosition | null {
		return dropReminderId === reminderId ? dropPosition : null
	}

	function isNoopDrop(
		sourceId: string,
		target: ReminderTreeItem,
		position: DropPosition
	): boolean {
		const source = findTreeItem(sourceId)
		if (!source) return true

		if (position === 'child') {
			const childSiblings = siblingsForParent(target.reminder.id)
			return (
				itemParentId(source) === target.reminder.id && childSiblings.at(-1)?.id === sourceId
			)
		}

		const nextParentId = itemParentId(target)
		if (itemParentId(source) !== nextParentId) return false

		const siblings = siblingsForParent(nextParentId)
		const sourceIndex = siblings.findIndex((item) => item.id === sourceId)
		const targetIndex = siblings.findIndex((item) => item.id === target.reminder.id)
		if (sourceIndex === -1 || targetIndex === -1) return false

		if (position === 'before') return sourceIndex === targetIndex - 1
		return sourceIndex === targetIndex + 1
	}

	function placeholderStyle(depth: number): string {
		return `margin-left: min(${Math.min(depth, 5) * 1.25}rem, 5rem);`
	}

	function handleDragStart(event: DragEvent, reminder: ReminderWithSubtasks): void {
		if (!canEditActiveList) return
		draggingReminderId = reminder.id
		event.dataTransfer?.setData('text/plain', reminder.id)
		if (event.dataTransfer) {
			event.dataTransfer.effectAllowed = 'move'
			const row = (event.currentTarget as HTMLElement | null)?.closest(
				'[data-reminder-row]'
			) as HTMLElement | null
			if (row) {
				const rect = row.getBoundingClientRect()
				event.dataTransfer.setDragImage(
					row,
					event.clientX - rect.left,
					event.clientY - rect.top
				)
			}
		}
	}

	function handleDragOver(event: DragEvent, target: ReminderTreeItem): void {
		if (
			!draggingReminderId ||
			draggingReminderId === target.reminder.id ||
			isDescendantOf(target.reminder.id, draggingReminderId)
		) {
			dropReminderId = null
			dropPosition = null
			return
		}
		event.preventDefault()
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
		setDropTarget(target, computeDropPosition(event, target))
	}

	function handlePlaceholderDragOver(
		event: DragEvent,
		target: ReminderTreeItem,
		position: DropPosition
	): void {
		if (!draggingReminderId) return
		event.preventDefault()
		if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
		setDropTarget(target, position)
	}

	async function handleDrop(event: DragEvent, target: ReminderTreeItem): Promise<void> {
		event.preventDefault()
		const sourceId = draggingReminderId ?? event.dataTransfer?.getData('text/plain') ?? null
		const position = dropReminderId === target.reminder.id ? dropPosition : null
		clearDragState()
		if (!sourceId || !position) return
		await repositionReminder(sourceId, target, position)
	}

	async function handlePlaceholderDrop(
		event: DragEvent,
		target: ReminderTreeItem,
		position: DropPosition
	): Promise<void> {
		event.preventDefault()
		const sourceId = draggingReminderId ?? event.dataTransfer?.getData('text/plain') ?? null
		clearDragState()
		if (!sourceId || isNoopDrop(sourceId, target, position)) return
		await repositionReminder(sourceId, target, position)
	}

	function dropTargetAtPoint(
		clientX: number,
		clientY: number
	): { target: ReminderTreeItem; position: DropPosition | null } | null {
		const element = document.elementFromPoint(clientX, clientY)
		const placeholder = element?.closest('[data-reminder-drop-id]') as HTMLElement | null
		if (placeholder) {
			const target = findTreeItem(placeholder.dataset.reminderDropId ?? null)
			const position = placeholder.dataset.reminderDropPosition
			if (target && (position === 'before' || position === 'after' || position === 'child')) {
				return { target, position }
			}
		}
		const row = element?.closest('[data-reminder-id]') as HTMLElement | null
		const target = findTreeItem(row?.dataset.reminderId ?? null)
		return target ? { target, position: null } : null
	}

	function updatePointerDrop(clientX: number, clientY: number): void {
		const hit = dropTargetAtPoint(clientX, clientY)
		const target = hit?.target ?? null
		if (
			!target ||
			!draggingReminderId ||
			draggingReminderId === target.reminder.id ||
			isDescendantOf(target.reminder.id, draggingReminderId)
		) {
			dropReminderId = null
			dropPosition = null
			return
		}
		if (hit?.position) {
			setDropTarget(target, hit.position)
			return
		}

		const row = document.querySelector(
			`[data-reminder-id="${target.reminder.id}"]`
		) as HTMLElement | null
		if (!row) return
		setDropTarget(target, computeDropPositionFromPoint(clientX, clientY, row, target))
	}

	function handlePointerDragStart(event: PointerEvent, reminder: ReminderWithSubtasks): void {
		if (!canEditActiveList || !browser) return
		if (event.pointerType === 'mouse') return
		event.preventDefault()
		pointerDragCleanup?.()
		draggingReminderId = reminder.id

		const handleMove = (moveEvent: PointerEvent) => {
			moveEvent.preventDefault()
			updatePointerDrop(moveEvent.clientX, moveEvent.clientY)
		}
		const handleUp = (upEvent: PointerEvent) => {
			upEvent.preventDefault()
			const target = findTreeItem(dropReminderId)
			const position = dropPosition
			clearDragState()
			if (!target || !position) return
			void repositionReminder(reminder.id, target, position)
		}
		const handleCancel = () => clearDragState()

		window.addEventListener('pointermove', handleMove, { passive: false })
		window.addEventListener('pointerup', handleUp, { once: true, passive: false })
		window.addEventListener('pointercancel', handleCancel, { once: true })
		pointerDragCleanup = () => {
			window.removeEventListener('pointermove', handleMove)
			window.removeEventListener('pointerup', handleUp)
			window.removeEventListener('pointercancel', handleCancel)
		}
		updatePointerDrop(event.clientX, event.clientY)
	}

	async function repositionReminder(
		sourceId: string,
		target: ReminderTreeItem,
		position: DropPosition
	): Promise<void> {
		if (!canEditActiveList) return
		if (sourceId === target.reminder.id) return
		if (isDescendantOf(target.reminder.id, sourceId)) return
		const source = findTreeItem(sourceId)
		if (!source) return
		const nextParentId = position === 'child' ? target.reminder.id : itemParentId(target)
		if (nextParentId === source.reminder.id) return

		const siblings = siblingsForParent(nextParentId).filter((r) => r.id !== sourceId)
		let insertIndex = siblings.length
		if (position !== 'child') {
			const targetIndex = siblings.findIndex((r) => r.id === target.reminder.id)
			if (targetIndex === -1) return
			insertIndex = position === 'before' ? targetIndex : targetIndex + 1
		}

		const ordered = [
			...siblings.slice(0, insertIndex),
			source.reminder,
			...siblings.slice(insertIndex),
		]
		const updates = ordered
			.map((reminder, index) => ({ reminder, index }))
			.filter(
				({ reminder, index }) =>
					(reminder.parent_id ?? null) !== nextParentId ||
					(reminder.position ?? 0) !== index
			)
		if (updates.length === 0) return
		const snapshot = cloneReminderTree(reminders.getReminders(listId))
		const optimistic = buildOptimisticReorder(sourceId, nextParentId, insertIndex)
		if (optimistic) reminders.setReminders(listId, optimistic)

		const results = await Promise.all(
			updates.map(({ reminder, index }) =>
				reminders.updateReminder(reminder, { parent_id: nextParentId, position: index })
			)
		)
		if (results.some((result) => result === null)) {
			reminders.setReminders(listId, snapshot)
			void reminders.loadReminders(listId, { force: true })
			return
		}
		await reminders.loadReminders(listId, { force: true })
		expandedReminderId = null
	}

	function getReminderMotion(id: string): {
		motion: 'in' | 'out-complete' | 'out-uncomplete' | null
		delayMs?: number
		iconMorph?: 'plus-to-circle' | null
	} {
		// check if transitioning
		const t = transitions.get(id)
		if (t) {
			return { motion: t.direction === 'to-completed' ? 'out-complete' : 'out-uncomplete' }
		}
		// check if incoming
		const entry = incoming.get(id)
		if (entry) {
			return { motion: 'in', delayMs: entry.delayMs, iconMorph: entry.iconMorph ?? null }
		}
		return { motion: null }
	}

	// actions

	async function startInlineAdd() {
		if (!canEditActiveList) return
		isAddingReminder = true
		isAddingExpanded = false
		expandedReminderId = null
		await tick()
		isAddingExpanded = true
	}

	async function cancelInlineAdd() {
		isAddingExpanded = false
		await new Promise((resolve) => setTimeout(resolve, 220))
		isAddingReminder = false
	}

	async function submitInlineAdd(draft: {
		title: string
		description: string | null
	}): Promise<boolean> {
		if (!canEditActiveList) return false
		const created = await reminders.createReminder({
			title: draft.title,
			listId,
			description: draft.description,
		})
		if (!created) return false

		isAddingReminder = false
		isAddingExpanded = false
		return true
	}

	async function loadReminders(targetListId: string | null) {
		const token = ++loadToken
		isLoading = true
		try {
			await reminders.loadReminders(targetListId)
		} finally {
			if (token === loadToken) isLoading = false
		}
	}

	async function toggleComplete(reminder: ReminderWithSubtasks) {
		if (!canEditActiveList) return
		const direction = reminder.status === 'pending' ? 'to-completed' : 'to-pending'

		if (!transitions.has(reminder.id)) {
			transitions.set(reminder.id, { direction, reminder: { ...reminder } })
			incoming.set(reminder.id, { delayMs: 0 })

			window.setTimeout(() => transitions.delete(reminder.id), MOTION_MS + 30)
			window.setTimeout(() => incoming.delete(reminder.id), MOTION_MS + 280)
		}

		if (direction === 'to-completed') {
			await reminders.completeReminder(reminder)
		} else {
			await reminders.uncompleteReminder(reminder)
		}
		if (reminder.parent_id) await reminders.loadReminders(listId, { force: true })
	}

	async function moveReminder(reminder: ReminderWithSubtasks, targetListId: string | null) {
		if (!canEditActiveList) return
		await reminders.moveReminder(reminder, targetListId)
		if (reminder.parent_id) await reminders.loadReminders(listId, { force: true })
		expandedReminderId = null
	}

	async function deleteReminder(reminder: ReminderWithSubtasks): Promise<boolean> {
		if (!canEditActiveList) return false
		const ok = await reminders.deleteReminder(reminder)
		if (ok && reminder.parent_id) await reminders.loadReminders(listId, { force: true })
		if (ok && expandedReminderId === reminder.id) {
			expandedReminderId = null
		}
		return ok
	}

	async function updateReminder(
		reminder: ReminderWithSubtasks,
		updates: ReminderUpdate
	): Promise<boolean> {
		if (!canEditActiveList) return false
		const saved = await reminders.updateReminder(reminder, updates)
		if (saved && (reminder.parent_id || 'parent_id' in updates || 'position' in updates)) {
			await reminders.loadReminders(listId, { force: true })
		}
		return Boolean(saved)
	}

	// effects

	$effect(() => {
		const currentListId = listId
		void untrack(() => {
			void loadReminders(currentListId)
			void reminders.loadLists()
		})
	})

	$effect(() => {
		if (activeList)
			void resourceAccess.ensure('reminder_list', activeList.id, activeList.owner_id)
	})

	$effect(() => {
		if (!browser) return
		const handler = (event: Event) => {
			if (!canEditActiveList) return
			const { detail } = event as CustomEvent<{ listId: string | null }>
			if (!detail) return
			if (detail.listId !== listId) return
			void startInlineAdd()
		}

		window.addEventListener('reminders:add', handler)
		return () => window.removeEventListener('reminders:add', handler)
	})

	$effect(() => {
		if (!browser) return
		if (!expandedReminderId && !isAddingReminder) return
		if (!canEditActiveList) {
			expandedReminderId = null
			isAddingReminder = false
			return
		}

		const onPointerDown = (event: PointerEvent) => {
			const target = event.target
			if (!(target instanceof HTMLElement)) return

			if (isAddingReminder) {
				if (target.closest('[data-reminder-draft="true"]')) return
			}

			if (expandedReminderId) {
				const selector = `[data-reminder-id="${expandedReminderId}"]`
				if (target.closest(selector)) return
			}

			if (isAddingReminder) {
				void cancelInlineAdd()
			}
			expandedReminderId = null
		}

		window.addEventListener('pointerdown', onPointerDown)
		return () => window.removeEventListener('pointerdown', onPointerDown)
	})

	onDestroy(() => {
		pointerDragCleanup?.()
	})
</script>

{#snippet dropPlaceholder(item: ReminderTreeItem, position: DropPosition)}
	<div
		role="presentation"
		class="px-3 py-1 transition-[height,opacity,transform] duration-150"
		style={placeholderStyle(position === 'child' ? item.depth + 1 : item.depth)}
		data-reminder-drop-id={item.reminder.id}
		data-reminder-drop-position={position}
		ondragover={(event) => handlePlaceholderDragOver(event, item, position)}
		ondrop={(event) => void handlePlaceholderDrop(event, item, position)}
	>
		<div
			class="h-9 rounded-3xl border border-dashed border-(--accent-primary)/45 bg-(--accent-primary)/10"
		></div>
	</div>
{/snippet}

<div class="flex w-full flex-1 flex-col" style="gap: var(--spacing-header-content);">
	{#if showListTitle}
		<header class="flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6">
			<div class="flex min-w-0 items-center gap-3">
				{#if activeList}
					<span
						class="rounded-pill text-foreground flex h-8 w-8 items-center justify-center"
						style:background-color={activeList.color ?? 'rgba(255,255,255,0.08)'}
					>
						<span class="text-sm">{activeList.icon ?? '📋'}</span>
					</span>
				{:else}
					<span
						class="rounded-pill bg-foreground/8 text-foreground/80 flex h-8 w-8 items-center justify-center"
					>
						<CheckBox variant="solid" class="h-5 w-5" />
					</span>
				{/if}
				<h2 class="text-foreground/90 min-w-0 truncate text-xl font-semibold tracking-wide">
					{activeList?.name ?? 'reminders'}
				</h2>
			</div>
		</header>
	{/if}

	{#if isLoading}
		<div class="flex flex-1 items-center justify-center">
			<NokodoLoader className="opacity-70" expanded={false} />
		</div>
	{:else}
		<div class="flex-1 px-1 pb-6 {showListTitle ? '' : 'pt-4'}">
			<div class="flex flex-col gap-1">
				{#each pendingReminderItems as item (item.reminder.id)}
					{@const reminder = item.reminder}
					{@const motion = getReminderMotion(reminder.id)}
					{#if getDropTarget(reminder.id) === 'before'}
						{@render dropPlaceholder(item, 'before')}
					{/if}
					<ReminderRow
						kind="edit"
						{reminder}
						depth={item.depth}
						isDragging={draggingReminderId === reminder.id}
						dropTarget={getDropTarget(reminder.id)}
						editable={canEditActiveList}
						expanded={expandedReminderId === reminder.id &&
							!transitions.has(reminder.id)}
						{availableLists}
						motion={motion.motion}
						motionDelayMs={motion.delayMs}
						iconMorph={motion.iconMorph}
						onToggleComplete={() => toggleComplete(reminder)}
						onMove={(targetListId) => moveReminder(reminder, targetListId)}
						onDelete={() => deleteReminder(reminder)}
						onSelect={() => {
							expandedReminderId = reminder.id
						}}
						onDeselect={() => {
							expandedReminderId = null
						}}
						onUpdate={(updates: ReminderUpdate) => updateReminder(reminder, updates)}
						onDragStart={(event) => handleDragStart(event, reminder)}
						onDragOver={(event) => handleDragOver(event, item)}
						onDrop={(event) => void handleDrop(event, item)}
						onDragEnd={clearDragState}
						onPointerDragStart={(event) => handlePointerDragStart(event, reminder)}
					/>
					{#if getDropTarget(reminder.id) === 'after'}
						{@render dropPlaceholder(item, 'after')}
					{:else if getDropTarget(reminder.id) === 'child'}
						{@render dropPlaceholder(item, 'child')}
					{/if}
				{/each}

				{#if isAddingReminder && canEditActiveList}
					<div class="px-1 py-1">
						<ReminderRow
							kind="create"
							{listId}
							expanded={isAddingExpanded}
							autoFocus={isAddingExpanded}
							onCreate={(draft: { title: string; description: string | null }) =>
								submitInlineAdd(draft)}
							onCancel={() => void cancelInlineAdd()}
						/>
					</div>
				{:else if canEditActiveList}
					<button
						type="button"
						class="rounded-pill text-foreground/70 hover:bg-foreground/6 hover:text-foreground/85 flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 text-left text-[0.95rem] leading-6 transition-colors duration-150"
						onclick={() => void startInlineAdd()}
					>
						<span class="text-foreground/55 flex h-6 w-6 items-center justify-center">
							<Plus class="h-6 w-6" strokeWidth="2" />
						</span>
						<span>new reminder</span>
					</button>
				{/if}
			</div>

			{#if completedCount > 0}
				<div class="mt-3 px-2">
					<button
						type="button"
						class="rounded-pill liquid-glass liquid-glass--frosted border-foreground/14 text-foreground flex w-full cursor-pointer items-center justify-between border px-4 py-2 text-left text-[0.95rem] font-semibold transition-colors duration-150 hover:brightness-110"
						onclick={() => (showCompleted = !showCompleted)}
					>
						<span>completed ({completedCount})</span>
						<span
							class="text-foreground/70 transition-transform {showCompleted
								? 'rotate-180'
								: ''}"
						>
							<ChevronDown class="h-4 w-4" />
						</span>
					</button>
				</div>

				<div
					class="mt-1 grid px-1 transition-[grid-template-rows,opacity,transform] duration-220 ease-out {showCompleted
						? 'translate-y-0 grid-rows-[1fr] opacity-100'
						: '-translate-y-1 grid-rows-[0fr] opacity-0'}"
					aria-hidden={!showCompleted}
				>
					<div class="min-h-0 overflow-hidden">
						<div class="flex flex-col gap-1 pt-1">
							{#each completedReminderItems as item (item.reminder.id)}
								{@const reminder = item.reminder}
								{@const motion = getReminderMotion(reminder.id)}
								{#if getDropTarget(reminder.id) === 'before'}
									{@render dropPlaceholder(item, 'before')}
								{/if}
								<ReminderRow
									kind="edit"
									{reminder}
									depth={item.depth}
									isDragging={draggingReminderId === reminder.id}
									dropTarget={getDropTarget(reminder.id)}
									editable={canEditActiveList}
									expanded={expandedReminderId === reminder.id &&
										!transitions.has(reminder.id)}
									{availableLists}
									motion={motion.motion}
									motionDelayMs={motion.delayMs}
									iconMorph={motion.iconMorph}
									onToggleComplete={() => toggleComplete(reminder)}
									onMove={(targetListId) => moveReminder(reminder, targetListId)}
									onDelete={() => deleteReminder(reminder)}
									onSelect={() => {
										expandedReminderId = reminder.id
									}}
									onDeselect={() => {
										expandedReminderId = null
									}}
									onUpdate={(updates: ReminderUpdate) =>
										updateReminder(reminder, updates)}
									onDragStart={(event) => handleDragStart(event, reminder)}
									onDragOver={(event) => handleDragOver(event, item)}
									onDrop={(event) => void handleDrop(event, item)}
									onDragEnd={clearDragState}
									onPointerDragStart={(event) =>
										handlePointerDragStart(event, reminder)}
								/>
								{#if getDropTarget(reminder.id) === 'after'}
									{@render dropPlaceholder(item, 'after')}
								{:else if getDropTarget(reminder.id) === 'child'}
									{@render dropPlaceholder(item, 'child')}
								{/if}
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
