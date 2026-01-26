<script lang="ts">
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Circle from '$lib/components/icons/Circle.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { ReminderWithSubtasks } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'

	interface Props {
		reminder: ReminderWithSubtasks
		expanded?: boolean
		onToggleComplete: () => void
		onDelete: () => void
		onSelect: () => void
		onDeselect: () => void
		onUpdate: (updates: { title?: string; description?: string | null }) => void
	}

	let {
		reminder,
		expanded = false,
		onToggleComplete,
		onDelete,
		onSelect,
		onDeselect,
		onUpdate,
	}: Props = $props()

	let isHoveringCircle = $state(false)
	let isMenuOpen = $state(false)
	let menuEl: HTMLDivElement | null = $state(null)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let titleInputEl: HTMLInputElement | null = $state(null)

	let editedTitle = $state('')
	let editedDescription = $state('')

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

	async function handleRowClick(event: MouseEvent) {
		const target = event.target as HTMLElement
		if (target.closest('[data-circle-button]') || target.closest('[data-menu-area]')) return

		if (!expanded) {
			onSelect()
			await tick()
			titleInputEl?.focus()
			titleInputEl?.select()
		}
	}

	function handleRowKeyDown(event: KeyboardEvent) {
		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()
		if (expanded) return
		onSelect()
		void tick().then(() => {
			titleInputEl?.focus()
			titleInputEl?.select()
		})
	}

	function handleTitleBlur() {
		const trimmed = editedTitle.trim()
		if (trimmed !== reminder.title && trimmed !== '') {
			onUpdate({ title: trimmed })
		} else {
			editedTitle = reminder.title
		}
	}

	function handleDescriptionBlur() {
		const trimmed = editedDescription.trim()
		const original = reminder.description ?? ''
		if (trimmed !== original) {
			onUpdate({ description: trimmed || null })
		}
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault()
			editedTitle = reminder.title
			editedDescription = reminder.description ?? ''
			onDeselect()
		}
	}

	$effect(() => {
		editedTitle = reminder.title
		editedDescription = reminder.description ?? ''
	})

	$effect(() => {
		if (!isMenuOpen) return

		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return
			event.preventDefault()
			isMenuOpen = false
		}

		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (menuEl && path.includes(menuEl)) return
			if (menuButtonEl && path.includes(menuButtonEl)) return
			isMenuOpen = false
		}

		window.addEventListener('keydown', onKeyDown)
		window.addEventListener('pointerdown', onPointerDown)
		return () => {
			window.removeEventListener('keydown', onKeyDown)
			window.removeEventListener('pointerdown', onPointerDown)
		}
	})
</script>

<div
	role="button"
	tabindex="0"
	class="group relative cursor-pointer transition-colors duration-150 {expanded
		? 'rounded-box border border-white/10 bg-white/6'
		: 'rounded-pill hover:bg-white/6'} {isCompleted ? 'opacity-65' : ''}"
	onclick={handleRowClick}
	onkeydown={handleRowKeyDown}
>
	<div class="flex items-center gap-3 px-3 py-2.5">
		<!-- circle/check button (no background shape) -->
		<button
			data-circle-button
			type="button"
			class="flex h-5 w-5 shrink-0 items-center justify-center text-white/55 transition-colors duration-150 hover:text-white/80 {isCompleted
				? 'text-emerald-400'
				: ''}"
			onclick={(e) => {
				e.stopPropagation()
				onToggleComplete()
			}}
			onmouseenter={() => (isHoveringCircle = true)}
			onmouseleave={() => (isHoveringCircle = false)}
			aria-label={isCompleted ? 'mark as pending' : 'mark as completed'}
		>
			{#if isCompleted || isHoveringCircle}
				<Check className="h-5 w-5" strokeWidth="2" />
			{:else}
				<Circle className="h-5 w-5" />
			{/if}
		</button>

		<!-- title -->
		<div class="min-w-0 flex-1">
			{#if expanded}
				<input
					bind:this={titleInputEl}
					type="text"
					class="w-full bg-transparent text-[0.95rem] leading-6 text-white/90 outline-none placeholder:text-white/40 {isCompleted
						? 'line-through'
						: ''}"
					placeholder="reminder title"
					bind:value={editedTitle}
					onblur={handleTitleBlur}
					onkeydown={handleKeyDown}
				/>
			{:else}
				<div
					class="min-w-0 truncate text-[0.95rem] leading-6 text-white/90 {isCompleted
						? 'line-through'
						: ''}"
				>
					{reminder.title}
				</div>
			{/if}
		</div>

		<!-- menu button -->
		<div data-menu-area class="flex items-center">
			<button
				bind:this={menuButtonEl}
				type="button"
				class="rounded-circle flex h-8 w-8 items-center justify-center text-white/55 transition-all duration-150 hover:bg-white/8 hover:text-white {device.isTouch ||
				!device.hasHover
					? 'opacity-100'
					: 'opacity-0 group-hover:opacity-100'}"
				onclick={(event) => {
					event.stopPropagation()
					isMenuOpen = !isMenuOpen
				}}
				aria-label="reminder actions"
			>
				<EllipsisHorizontal className="h-4 w-4" />
			</button>
		</div>
	</div>

	<!-- expanded details -->
	{#if expanded}
		<div class="space-y-3 px-3 pt-1 pb-3">
			<!-- description -->
			<textarea
				class="w-full resize-none bg-transparent pl-8 text-sm leading-5 text-white/70 outline-none placeholder:text-white/35"
				placeholder="add details"
				rows="2"
				bind:value={editedDescription}
				onblur={handleDescriptionBlur}
				onkeydown={handleKeyDown}
			></textarea>

			<!-- date/time and repeat -->
			<div class="flex flex-wrap items-center gap-2 pl-8">
				<button
					type="button"
					class="rounded-pill flex items-center gap-1.5 border border-white/10 bg-white/4 px-3 py-1.5 text-xs transition-colors hover:bg-white/8 {hasDueDate
						? isOverdue
							? 'text-red-400'
							: 'text-white/70'
						: 'text-white/45'}"
				>
					<Calendar className="h-3.5 w-3.5" />
					<span>{hasDueDate ? formattedDueDate : 'add date/time'}</span>
				</button>

				<button
					type="button"
					class="rounded-pill flex items-center gap-1.5 border border-white/10 bg-white/4 px-3 py-1.5 text-xs text-white/45 transition-colors hover:bg-white/8"
				>
					<ArrowPath className="h-3.5 w-3.5" />
					<span>repeat</span>
				</button>
			</div>
		</div>
	{:else if hasDueDate || reminder.description}
		<!-- collapsed but has extra info: show small indicator -->
		<div class="flex items-center gap-2 px-3 pb-2 pl-11">
			{#if hasDueDate}
				<span class="text-xs {isOverdue ? 'text-red-400' : 'text-white/45'}">
					{formattedDueDate}
				</span>
			{/if}
		</div>
	{/if}

	<!-- menu dropdown -->
	{#if isMenuOpen}
		<div
			bind:this={menuEl}
			class="rounded-box absolute top-full right-2 z-50 mt-2 w-44 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
		>
			<button
				type="button"
				class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
				onclick={(event) => {
					event.stopPropagation()
					isMenuOpen = false
					onSelect()
				}}
			>
				edit
			</button>
			<button
				type="button"
				class="rounded-pill mt-1 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
				onclick={(event) => {
					event.stopPropagation()
					isMenuOpen = false
					onDelete()
				}}
			>
				delete
			</button>
		</div>
	{/if}
</div>
