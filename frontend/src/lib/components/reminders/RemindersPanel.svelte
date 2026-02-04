<script lang="ts">
	import { browser } from '$app/environment'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import CheckBox from '$lib/components/icons/CheckBox.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import { reminders, type ReminderWithSubtasks } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import { SvelteMap } from 'svelte/reactivity'
	import ReminderRow from './ReminderRow.svelte'

	interface Props {
		listId: string | null
		showListTitle?: boolean
	}

	let { listId, showListTitle = false }: Props = $props()

	// ─────────────────────────────────────────────────────────────────────────
	// state
	// ─────────────────────────────────────────────────────────────────────────

	let isLoading = $state(true)
	let showCompleted = $state(false)
	let isAddingReminder = $state(false)
	let isAddingExpanded = $state(false)
	let expandedReminderId = $state<string | null>(null)

	/** animation state for reminders transitioning between pending/completed */
	interface TransitionEntry {
		direction: 'to-completed' | 'to-pending'
		reminder: ReminderWithSubtasks
	}
	const transitions = new SvelteMap<string, TransitionEntry>()

	/** animation state for reminders entering the list */
	interface IncomingEntry {
		delayMs: number
		iconMorph?: 'plus-to-circle' | null
	}
	const incoming = new SvelteMap<string, IncomingEntry>()

	const MOTION_MS = 420

	// ─────────────────────────────────────────────────────────────────────────
	// derived
	// ─────────────────────────────────────────────────────────────────────────

	const remindersList = $derived(reminders.getReminders(listId))
	const completedCount = $derived(remindersList.filter((r) => r.status === 'completed').length)

	/** pending reminders - exclude items currently transitioning out */
	const pendingReminders = $derived.by(() => {
		return remindersList.filter((r) => {
			// show transitioning-to-completed items until animation done
			const t = transitions.get(r.id)
			if (t?.direction === 'to-completed') return true
			// normal pending items (not transitioning to pending from completed)
			return r.status === 'pending' && !t
		})
	})

	/** completed reminders - exclude items currently transitioning out */
	const completedReminders = $derived.by(() => {
		return remindersList.filter((r) => {
			// show transitioning-to-pending items until animation done
			const t = transitions.get(r.id)
			if (t?.direction === 'to-pending') return true
			// normal completed items (not transitioning to completed from pending)
			return r.status === 'completed' && !t
		})
	})

	const availableLists = $derived(reminders.lists)
	const activeList = $derived(listId ? reminders.getListById(listId) : null)

	// ─────────────────────────────────────────────────────────────────────────
	// helpers
	// ─────────────────────────────────────────────────────────────────────────

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

	// ─────────────────────────────────────────────────────────────────────────
	// actions
	// ─────────────────────────────────────────────────────────────────────────

	async function startInlineAdd() {
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

	async function submitInlineAdd(draft: { title: string; description: string | null }) {
		const created = await reminders.createReminder({
			title: draft.title,
			listId,
			description: draft.description,
		})
		isAddingReminder = false
		isAddingExpanded = false
		if (created) {
			incoming.set(created.id, { delayMs: 0, iconMorph: 'plus-to-circle' })
			window.setTimeout(() => incoming.delete(created.id), 280)
		}
	}

	async function loadReminders() {
		isLoading = true
		try {
			await reminders.loadReminders(listId)
		} finally {
			isLoading = false
		}
	}

	async function toggleComplete(reminder: ReminderWithSubtasks) {
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
	}

	async function moveReminder(reminder: ReminderWithSubtasks, targetListId: string | null) {
		await reminders.moveReminder(reminder, targetListId)
		expandedReminderId = null
	}

	async function deleteReminder(reminder: ReminderWithSubtasks): Promise<boolean> {
		const ok = await reminders.deleteReminder(reminder)
		if (ok && expandedReminderId === reminder.id) {
			expandedReminderId = null
		}
		return ok
	}

	async function updateReminder(
		reminder: ReminderWithSubtasks,
		updates: { title?: string; description?: string | null }
	) {
		await reminders.updateReminder(reminder, updates)
	}

	// ─────────────────────────────────────────────────────────────────────────
	// effects
	// ─────────────────────────────────────────────────────────────────────────

	$effect(() => {
		void loadReminders()
		void reminders.loadListsAndCounts()
	})

	$effect(() => {
		if (!browser) return
		const handler = (event: Event) => {
			const { detail } = event as CustomEvent<{ listId: string | null }>
			if (!detail) return
			if (detail.listId !== listId) return
			void startInlineAdd()
		}

		window.addEventListener('nokodo:reminders:add', handler)
		return () => window.removeEventListener('nokodo:reminders:add', handler)
	})

	$effect(() => {
		if (!browser) return
		if (!expandedReminderId && !isAddingReminder) return

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
</script>

<div class="flex h-full min-h-0 flex-col" style="gap: var(--spacing-header-content);">
	{#if showListTitle}
		<header class="flex max-h-22 items-center justify-between gap-3 px-2 py-5 pb-6">
			<div class="flex min-w-0 items-center gap-3">
				{#if activeList}
					<span
						class="rounded-pill flex h-8 w-8 items-center justify-center text-white"
						style:background-color={activeList.color ?? 'rgba(255,255,255,0.08)'}
					>
						<span class="text-sm">{activeList.icon ?? '📋'}</span>
					</span>
				{:else}
					<span
						class="rounded-pill flex h-8 w-8 items-center justify-center bg-white/8 text-white/80"
					>
						<CheckBox variant="solid" class="h-5 w-5" />
					</span>
				{/if}
				<h2 class="min-w-0 truncate text-xl font-semibold tracking-wide text-white/90">
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
		<div class="min-h-0 flex-1 overflow-y-auto px-1 pb-2 {showListTitle ? '' : 'pt-4'}">
			<div class="flex flex-col gap-1">
				{#each pendingReminders as reminder (reminder.id)}
					{@const motion = getReminderMotion(reminder.id)}
					<ReminderRow
						kind="edit"
						{reminder}
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
						onUpdate={(updates: { title?: string; description?: string | null }) =>
							updateReminder(reminder, updates)}
					/>
				{/each}

				{#if isAddingReminder}
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
				{:else}
					<button
						type="button"
						class="rounded-pill flex w-full cursor-pointer items-center gap-3 px-3 py-2.5 text-left text-[0.95rem] leading-6 text-white/70 transition-colors duration-150 hover:bg-white/6 hover:text-white/85"
						onclick={() => void startInlineAdd()}
					>
						<span class="flex h-6 w-6 items-center justify-center text-white/55">
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
						class="rounded-pill flex w-full cursor-pointer items-center justify-between border border-white/10 bg-white/6 px-4 py-2 text-left text-[0.95rem] font-semibold text-white transition-colors duration-150 hover:bg-white/8"
						onclick={() => (showCompleted = !showCompleted)}
					>
						<span>completed ({completedCount})</span>
						<span
							class="text-white/70 transition-transform {showCompleted
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
							{#each completedReminders as reminder (reminder.id)}
								{@const motion = getReminderMotion(reminder.id)}
								<ReminderRow
									kind="edit"
									{reminder}
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
									onUpdate={(updates: {
										title?: string
										description?: string | null
									}) => updateReminder(reminder, updates)}
								/>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
