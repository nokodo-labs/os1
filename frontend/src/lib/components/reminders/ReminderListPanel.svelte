<script lang="ts">
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { reminders, type ReminderWithSubtasks } from '$lib/stores/reminders.svelte'
	import ReminderItem from './ReminderItem.svelte'

	interface Props {
		listId: string | null
		showListTitle?: boolean
	}

	let { listId, showListTitle = false }: Props = $props()

	let isLoading = $state(true)
	let showCompleted = $state(false)

	const remindersList = $derived(reminders.getReminders(listId))
	const pendingReminders = $derived(remindersList.filter((r) => r.status === 'pending'))
	const completedReminders = $derived(remindersList.filter((r) => r.status === 'completed'))

	async function loadReminders() {
		isLoading = true
		try {
			await reminders.loadReminders(listId)
		} finally {
			isLoading = false
		}
	}

	async function toggleComplete(reminder: ReminderWithSubtasks) {
		if (reminder.status === 'pending') {
			await reminders.completeReminder(reminder)
		} else {
			await reminders.uncompleteReminder(reminder)
		}
	}

	async function deleteReminder(reminder: ReminderWithSubtasks) {
		await reminders.deleteReminder(reminder)
	}

	$effect(() => {
		void loadReminders()
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
		<div class="min-h-0 flex-1 overflow-y-auto px-1 pb-2">
			{#if pendingReminders.length === 0 && completedReminders.length === 0}
				<div class="table h-full w-full">
					<div class="table-cell px-4 py-8 text-center align-middle">
						<div class="text-sm text-white/83">no reminders yet</div>
						<div class="text-xs text-white/66">use the plus button in the island</div>
					</div>
				</div>
			{:else}
				<div class="space-y-1">
					{#each pendingReminders as reminder (reminder.id)}
						<ReminderItem
							{reminder}
							onToggleComplete={() => toggleComplete(reminder)}
							onDelete={() => deleteReminder(reminder)}
						/>
					{/each}
				</div>

				{#if completedReminders.length > 0}
					<div class="mt-3 px-2">
						<button
							type="button"
							class="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/6 px-4 py-2 text-left text-sm text-white/75 transition-colors duration-150 hover:bg-white/8"
							onclick={() => (showCompleted = !showCompleted)}
						>
							<span>completed ({completedReminders.length})</span>
							<span
								class="text-white/50 transition-transform {showCompleted
									? 'rotate-180'
									: ''}"
							>
								▼
							</span>
						</button>
					</div>

					{#if showCompleted}
						<div class="mt-1 space-y-1 px-1">
							{#each completedReminders as reminder (reminder.id)}
								<ReminderItem
									{reminder}
									onToggleComplete={() => toggleComplete(reminder)}
									onDelete={() => deleteReminder(reminder)}
								/>
							{/each}
						</div>
					{/if}
				{/if}
			{/if}
		</div>
	{/if}
</div>
