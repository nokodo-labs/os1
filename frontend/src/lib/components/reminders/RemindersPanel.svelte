<script lang="ts">
	import { browser } from '$app/environment'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import { reminders, type ReminderWithSubtasks } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import ReminderRow from './ReminderRow.svelte'

	interface Props {
		listId: string | null
		showListTitle?: boolean
	}

	let { listId, showListTitle = false }: Props = $props()

	let isLoading = $state(true)
	let showCompleted = $state(false)
	let isAddingReminder = $state(false)
	let isAddingExpanded = $state(false)
	let expandedReminderId = $state<string | null>(null)
	let transitions = $state<
		{
			id: string
			direction: 'to-completed' | 'to-pending'
			reminder: ReminderWithSubtasks
		}[]
	>([])
	let incoming = $state<{ id: string; delayMs: number; iconMorph?: 'plus-to-circle' | null }[]>(
		[]
	)

	const MOTION_MS = 420

	const remindersList = $derived(reminders.getReminders(listId))
	const completedCount = $derived(remindersList.filter((r) => r.status === 'completed').length)
	const pendingReminders = $derived.by(() => {
		const transitionIds = new Set(transitions.map((t) => t.id))
		return remindersList.filter((r) => r.status === 'pending' && !transitionIds.has(r.id))
	})
	const completedReminders = $derived.by(() => {
		const transitionIds = new Set(transitions.map((t) => t.id))
		return remindersList.filter((r) => r.status === 'completed' && !transitionIds.has(r.id))
	})
	const availableLists = $derived(reminders.lists)

	function motionForReminder(id: string): {
		motion: 'in' | null
		delayMs?: number
		iconMorph?: 'plus-to-circle' | null
	} {
		const entry = incoming.find((x) => x.id === id)
		if (!entry) return { motion: null }
		return { motion: 'in', delayMs: entry.delayMs, iconMorph: entry.iconMorph ?? null }
	}

	async function startInlineAdd() {
		isAddingReminder = true
		isAddingExpanded = false
		expandedReminderId = null
		await tick()
		isAddingExpanded = true
	}

	async function cancelInlineAdd() {
		// collapse animation first
		isAddingExpanded = false
		// wait for animation to finish before removing element
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
			// new reminder enters with a plus→circle icon morph
			incoming = [
				...incoming.filter((x) => x.id !== created.id),
				{ id: created.id, delayMs: 0, iconMorph: 'plus-to-circle' },
			]
			window.setTimeout(() => {
				incoming = incoming.filter((x) => x.id !== created.id)
			}, 280)
			expandedReminderId = created.id
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
		// capture direction BEFORE optimistic update changes status
		const direction = reminder.status === 'pending' ? 'to-completed' : 'to-pending'

		// start animation with captured direction
		const exists = transitions.some((t) => t.id === reminder.id)
		if (!exists) {
			transitions = [
				...transitions,
				{ id: reminder.id, direction, reminder: { ...reminder } },
			]
			// we hide transitioning ids from both lists, so the incoming row appears when the transition clears
			incoming = [
				...incoming.filter((x) => x.id !== reminder.id),
				{ id: reminder.id, delayMs: 0 },
			]

			window.setTimeout(() => {
				transitions = transitions.filter((t) => t.id !== reminder.id)
			}, MOTION_MS + 30)
			window.setTimeout(() => {
				incoming = incoming.filter((x) => x.id !== reminder.id)
			}, MOTION_MS + 280)
		}

		// then trigger optimistic store update (which immediately flips status in cache)
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

	async function deleteReminder(reminder: ReminderWithSubtasks) {
		await reminders.deleteReminder(reminder)
		if (expandedReminderId === reminder.id) {
			expandedReminderId = null
		}
	}

	async function updateReminder(
		reminder: ReminderWithSubtasks,
		updates: { title?: string; description?: string | null }
	) {
		await reminders.updateReminder(reminder, updates)
	}

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

<div class="flex h-full min-h-0 flex-col">
	{#if showListTitle}
		<header class="flex items-center gap-2 px-2 pt-2 pb-4">
			<!-- intentionally optional; master area already shows selection -->
			<h1 class="min-w-0 truncate text-lg font-semibold text-white/90">reminders</h1>
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
					{@const motion = motionForReminder(reminder.id)}
					<ReminderRow
						kind="edit"
						{reminder}
						expanded={expandedReminderId === reminder.id}
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

				{#each transitions.filter((t) => t.direction === 'to-completed') as t (t.id)}
					<ReminderRow
						kind="edit"
						reminder={t.reminder}
						expanded={false}
						{availableLists}
						motion="out-complete"
						onToggleComplete={() => {}}
						onMove={() => {}}
						onDelete={() => {}}
						onSelect={() => {}}
						onDeselect={() => {}}
						onUpdate={() => {}}
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
						class="rounded-pill flex w-full items-center gap-3 px-3 py-2.5 text-left text-[0.95rem] leading-6 text-white/70 transition-colors duration-150 hover:bg-white/6 hover:text-white/85"
						onclick={() => void startInlineAdd()}
					>
						<span class="flex h-6 w-6 items-center justify-center text-white/55">
							<Plus className="h-5 w-5" strokeWidth="2" />
						</span>
						<span>new reminder</span>
					</button>
				{/if}
			</div>

			{#if completedCount > 0 || transitions.some((t) => t.direction === 'to-pending')}
				<div class="mt-3 px-2">
					<button
						type="button"
						class="rounded-pill flex w-full items-center justify-between border border-white/10 bg-white/6 px-4 py-2 text-left text-[0.95rem] font-semibold text-white transition-colors duration-150 hover:bg-white/8"
						onclick={() => (showCompleted = !showCompleted)}
					>
						<span>completed ({completedCount})</span>
						<span
							class="text-white/70 transition-transform {showCompleted
								? 'rotate-180'
								: ''}"
						>
							<ChevronDown className="h-4 w-4" />
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
								{@const motion = motionForReminder(reminder.id)}
								<ReminderRow
									kind="edit"
									{reminder}
									expanded={expandedReminderId === reminder.id}
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

							{#each transitions.filter((t) => t.direction === 'to-pending') as t (t.id)}
								<ReminderRow
									kind="edit"
									reminder={t.reminder}
									expanded={false}
									{availableLists}
									motion="out-uncomplete"
									onToggleComplete={() => {}}
									onMove={() => {}}
									onDelete={() => {}}
									onSelect={() => {}}
									onDeselect={() => {}}
									onUpdate={() => {}}
								/>
							{/each}
						</div>
					</div>
				</div>
			{/if}
		</div>
	{/if}
</div>
