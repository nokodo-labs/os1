<script lang="ts">
	import type { components } from '$lib/api/types'
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte'
	import Circle from '$lib/components/icons/Circle.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'

	type Reminder = components['schemas']['ReminderWithSubtasks']

	interface Props {
		reminder: Reminder
		onToggleComplete: () => void
		onDelete: () => void
	}

	let { reminder, onToggleComplete, onDelete }: Props = $props()

	let showActions = $state(false)

	const isCompleted = $derived(reminder.status === 'completed')
	const hasDueDate = $derived(reminder.due_at != null)
	const formattedDueDate = $derived.by(() => {
		if (!reminder.due_at) return null
		const date = new Date(reminder.due_at)
		const now = new Date()
		const isToday = date.toDateString() === now.toDateString()
		const tomorrow = new Date(now)
		tomorrow.setDate(tomorrow.getDate() + 1)
		const isTomorrow = date.toDateString() === tomorrow.toDateString()

		if (isToday) return 'today'
		if (isTomorrow) return 'tomorrow'

		return date.toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
		})
	})

	const isOverdue = $derived.by(() => {
		if (!reminder.due_at || isCompleted) return false
		return new Date(reminder.due_at) < new Date()
	})
</script>

<div
	role="listitem"
	class="group flex items-start gap-3 rounded-2xl px-3 py-2.5 transition-colors duration-150 hover:bg-white/6 {isCompleted
		? 'opacity-65'
		: ''}"
	onmouseenter={() => (showActions = true)}
	onmouseleave={() => (showActions = false)}
>
	<button
		type="button"
		class="mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-white/4 text-white/55 transition-colors duration-150 hover:bg-white/8 hover:text-white/80 {isCompleted
			? 'text-emerald-400'
			: ''}"
		onclick={onToggleComplete}
		aria-label={isCompleted ? 'mark as pending' : 'mark as completed'}
	>
		{#if isCompleted}
			<CheckCircle className="h-5 w-5" />
		{:else}
			<Circle className="h-5 w-5" />
		{/if}
	</button>

	<div class="min-w-0 flex-1">
		<div
			class="min-w-0 truncate text-[0.95rem] leading-6 text-white/90 {isCompleted
				? 'line-through'
				: ''}"
		>
			{reminder.title}
		</div>
		{#if reminder.description}
			<div class="min-w-0 truncate text-sm text-white/55">
				{reminder.description}
			</div>
		{/if}
		{#if hasDueDate}
			<div class="mt-0.5 text-xs {isOverdue ? 'text-red-400' : 'text-white/45'}">
				{formattedDueDate}
			</div>
		{/if}
	</div>

	<div class="flex items-center">
		<button
			type="button"
			class="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-white/55 opacity-0 transition-all duration-150 group-hover:opacity-100 hover:bg-red-500/10 hover:text-red-400 {showActions
				? 'opacity-100'
				: ''}"
			onclick={onDelete}
			aria-label="delete reminder"
		>
			<Trash className="h-4 w-4" />
		</button>
	</div>
</div>
