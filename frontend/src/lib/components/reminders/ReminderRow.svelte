<script lang="ts">
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Circle from '$lib/components/icons/Circle.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { ReminderListWithCounts, ReminderWithSubtasks } from '$lib/stores/reminders.svelte'
	import { tick } from 'svelte'
	import { SvelteDate } from 'svelte/reactivity'

	type Motion = 'in' | 'out-complete' | 'out-uncomplete' | null

	type EditProps = {
		kind: 'edit'
		reminder: ReminderWithSubtasks
		expanded: boolean
		iconMorph?: 'plus-to-circle' | null
		onSelect: () => void
		onDeselect: () => void
		onToggleComplete: () => void | Promise<void>
		onMove: (targetListId: string | null) => void | Promise<void>
		onDelete: () => void | boolean | Promise<void | boolean>
		onUpdate: (updates: { title?: string; description?: string | null }) => void | Promise<void>
		availableLists: ReminderListWithCounts[]
		motion?: Motion
		motionDelayMs?: number
	}

	type CreateProps = {
		kind: 'create'
		listId: string | null
		expanded: boolean
		onCreate: (draft: { title: string; description: string | null }) => void | Promise<void>
		onCancel: () => void
		autoFocus?: boolean
		motion?: Motion
		motionDelayMs?: number
	}

	type Props = EditProps | CreateProps

	let props: Props = $props()

	let rootEl: HTMLDivElement | null = $state(null)
	let menuEl: HTMLDivElement | null = $state(null)
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let titleInputEl: HTMLInputElement | null = $state(null)

	let isMenuOpen = $state(false)

	let editedTitle = $state('')
	let editedDescription = $state('')

	const isCompleted = $derived(props.kind === 'edit' && props.reminder.status === 'completed')
	const isMotionIn = $derived(props.motion === 'in')
	const isMotionOutComplete = $derived(props.motion === 'out-complete')
	const isMotionOutUncomplete = $derived(props.motion === 'out-uncomplete')
	const isMorphPlus = $derived(props.kind === 'edit' && props.iconMorph === 'plus-to-circle')
	const hasDueDate = $derived(props.kind === 'edit' && props.reminder.due_at != null)
	const formattedDueDate = $derived.by(() => {
		if (props.kind !== 'edit') return null
		if (!props.reminder.due_at) return null

		const date = new SvelteDate(props.reminder.due_at)
		const now = new SvelteDate()
		const isToday = date.toDateString() === now.toDateString()
		const tomorrow = new SvelteDate(now)
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
		if (props.kind !== 'edit') return false
		if (!props.reminder.due_at || props.reminder.status === 'completed') return false
		return new SvelteDate(props.reminder.due_at) < new SvelteDate()
	})

	async function focusTitle() {
		await tick()
		titleInputEl?.focus()
		if (titleInputEl) {
			const end = titleInputEl.value.length
			titleInputEl.setSelectionRange(end, end)
		}
	}

	async function handleRowClick(event: MouseEvent) {
		const target = event.target as HTMLElement
		if (target.closest('[data-circle-button]') || target.closest('[data-menu-area]')) return

		if (!props.expanded) {
			if (props.kind === 'create') return
			props.onSelect()
			await focusTitle()
		}
	}

	function handleTitleBlur() {
		const trimmed = editedTitle.trim()

		if (props.kind === 'edit') {
			if (trimmed !== props.reminder.title && trimmed !== '') {
				props.onUpdate({ title: trimmed })
			} else {
				editedTitle = props.reminder.title
			}
			return
		}

		editedTitle = trimmed
	}

	function handleDescriptionBlur() {
		const trimmed = editedDescription.trim()

		if (props.kind === 'edit') {
			const original = props.reminder.description ?? ''
			if (trimmed !== original) {
				props.onUpdate({ description: trimmed || null })
			}
			return
		}

		editedDescription = trimmed
	}

	function resetEditDraft() {
		if (props.kind !== 'edit') return
		editedTitle = props.reminder.title
		editedDescription = props.reminder.description ?? ''
	}

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.preventDefault()

			if (props.kind === 'create') {
				props.onCancel()
				return
			}

			resetEditDraft()
			props.onDeselect()
			return
		}
	}

	function handleTitleKeyDown(event: KeyboardEvent) {
		handleKeyDown(event)
		// enter (without shift) submits/saves
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault()
			if (props.kind === 'create') {
				if (editedTitle.trim() !== '') {
					void submitCreate()
				}
			} else {
				titleInputEl?.blur()
			}
		}
	}

	function handleDescriptionKeyDown(event: KeyboardEvent) {
		// escape handled by base handler
		if (event.key === 'Escape') {
			handleKeyDown(event)
			return
		}
		// shift+enter: allow newline (default textarea behavior)
		// enter without shift: blur to save
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault()
			;(event.target as HTMLTextAreaElement | null)?.blur()
		}
	}

	function handleRowKeyDown(event: KeyboardEvent) {
		// ignore if the event came from an input or textarea (let them handle their own input)
		const target = event.target as HTMLElement
		if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()

		if (props.kind === 'create') return
		if (props.expanded) return
		props.onSelect()
		void focusTitle()
	}

	async function submitCreate() {
		if (props.kind !== 'create') return
		const title = editedTitle.trim()
		if (title === '') {
			props.onCancel()
			return
		}

		await props.onCreate({
			title,
			description: editedDescription.trim() || null,
		})
	}

	async function handleToggleComplete() {
		if (props.kind !== 'edit') return
		await props.onToggleComplete()
	}

	$effect(() => {
		if (props.kind !== 'edit') return
		editedTitle = props.reminder.title
		editedDescription = props.reminder.description ?? ''
	})

	$effect(() => {
		if (props.kind !== 'create') return
		if (!props.autoFocus) return
		if (!props.expanded) return
		void focusTitle()
	})

	$effect(() => {
		if (props.kind !== 'edit') return
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
	bind:this={rootEl}
	data-reminder-row
	data-reminder-id={props.kind === 'edit' ? props.reminder.id : undefined}
	data-reminder-draft={props.kind === 'create' ? 'true' : undefined}
	role="button"
	tabindex="0"
	style={props.motionDelayMs
		? `--reminder-motion-delay-ms: ${props.motionDelayMs}ms;`
		: undefined}
	class="reminder-row group relative cursor-pointer overflow-visible transition-colors duration-150 {props.expanded
		? 'rounded-box border border-white/10 bg-white/6'
		: 'rounded-pill hover:bg-white/6'} {isCompleted
		? 'is-completed opacity-65'
		: ''} {isMotionIn ? 'is-incoming' : ''} {isMotionOutComplete
		? 'is-out is-out-complete'
		: ''} {isMotionOutUncomplete ? 'is-out is-out-uncomplete' : ''} {isMorphPlus
		? 'morph-plus'
		: ''}"
	onclick={handleRowClick}
	onkeydown={handleRowKeyDown}
>
	<div class="flex items-center gap-3 px-3 py-2.5">
		<button
			data-circle-button
			type="button"
			class="circle-btn flex h-6 w-6 shrink-0 items-center justify-center text-white/55 transition-colors duration-150 {props.kind ===
			'edit'
				? 'hover:text-white/80'
				: ''} {isCompleted ? 'text-emerald-400' : ''}"
			onclick={(event) => {
				event.stopPropagation()
				void handleToggleComplete()
			}}
			aria-label={props.kind === 'edit'
				? isCompleted
					? 'mark as pending'
					: 'mark as completed'
				: 'add reminder'}
		>
			{#if props.kind === 'create'}
				<span class="plus-icon" aria-hidden="true">
					<Plus className="h-6 w-6" strokeWidth="2" />
				</span>
			{:else}
				<span class="plus-icon plus-overlay" aria-hidden="true">
					<Plus className="h-6 w-6" strokeWidth="2" />
				</span>
				<span class="circle-icon" aria-hidden="true">
					<Circle className="h-6 w-6" />
				</span>
				<span class="check-icon" aria-hidden="true">
					<Check className="h-6 w-6" strokeWidth="2" />
				</span>
			{/if}
		</button>

		<div class="min-w-0 flex-1">
			{#if props.expanded}
				<div class="relative min-w-0">
					<input
						bind:this={titleInputEl}
						type="text"
						class="title-input w-full bg-transparent text-[0.95rem] leading-6 text-white/90 outline-none placeholder:text-white/40 {isCompleted
							? 'line-through'
							: ''}"
						placeholder={props.kind === 'create' ? 'new reminder' : 'reminder title'}
						autocomplete="off"
						bind:value={editedTitle}
						onblur={handleTitleBlur}
						onkeydown={handleTitleKeyDown}
					/>
					<span class="title-text title-overlay" aria-hidden="true">{editedTitle}</span>
				</div>
			{:else}
				<div class="min-w-0 truncate text-[0.95rem] leading-6 text-white/90">
					<span class="title-text">
						{props.kind === 'edit' ? props.reminder.title : editedTitle}
					</span>
				</div>
			{/if}
		</div>

		{#if props.kind === 'edit'}
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
		{/if}
	</div>

	<div class="details-shell {props.expanded ? 'expanded' : ''}">
		<div class="details-inner">
			<div class="space-y-3 px-3 pt-1 pb-3">
				<textarea
					class="w-full resize-none bg-transparent pl-8 text-sm leading-5 text-white/70 outline-none placeholder:text-white/35"
					placeholder="add details"
					rows="2"
					bind:value={editedDescription}
					onblur={handleDescriptionBlur}
					onkeydown={handleDescriptionKeyDown}
				></textarea>

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

					{#if props.kind === 'create'}
						<button
							type="button"
							class="rounded-pill ml-auto border border-white/10 bg-white/8 px-3 py-1.5 text-xs font-medium text-white/85 transition-colors hover:bg-white/12 disabled:opacity-45"
							onclick={(event) => {
								event.stopPropagation()
								void submitCreate()
							}}
							disabled={editedTitle.trim() === ''}
						>
							save
						</button>
					{/if}
				</div>
			</div>
		</div>
	</div>

	{#if props.kind === 'edit' && (hasDueDate || props.reminder.description) && !props.expanded}
		<div class="flex items-center gap-2 px-3 pb-2 pl-11">
			{#if hasDueDate}
				<span class="text-xs {isOverdue ? 'text-red-400' : 'text-white/45'}">
					{formattedDueDate}
				</span>
			{/if}
		</div>
	{/if}

	{#if props.kind === 'edit' && isMenuOpen}
		<div
			bind:this={menuEl}
			class="rounded-box absolute top-full right-2 z-50 mt-2 w-56 border border-white/10 bg-black/70 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] backdrop-blur"
		>
			<div class="px-3 pt-2 pb-1 text-xs font-medium text-white/55">move</div>
			<div class="max-h-44 overflow-auto">
				<button
					type="button"
					class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
					onclick={(event) => {
						event.stopPropagation()
						isMenuOpen = false
						void props.onMove(null)
					}}
				>
					reminders
				</button>

				{#each props.availableLists as list (list.id)}
					<button
						type="button"
						class="rounded-pill flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm text-white/80 transition-colors duration-150 hover:bg-white/10"
						onclick={(event) => {
							event.stopPropagation()
							isMenuOpen = false
							void props.onMove(list.id)
						}}
					>
						{list.name}
					</button>
				{/each}
			</div>

			<div class="mt-1">
				<DeleteButton
					confirm={true}
					stopPropagation={true}
					modalText={{
						title: 'delete reminder?',
						description: props.kind === 'edit' ? props.reminder.title : '',
					}}
					onDelete={() => {
						if (props.kind !== 'edit') return true
						return props.onDelete()
					}}
				/>
			</div>
		</div>
	{/if}
</div>

<style>
	.reminder-row {
		max-height: 360px;
	}

	.details-shell {
		display: grid;
		grid-template-rows: 0fr;
		opacity: 0;
		transition:
			grid-template-rows 180ms ease,
			opacity 180ms ease;
	}

	.details-shell.expanded {
		grid-template-rows: 1fr;
		opacity: 1;
	}

	.details-inner {
		overflow: hidden;
	}

	.circle-btn {
		position: relative;
	}

	.plus-icon {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		opacity: 1;
		transform: scale(1);
		transition:
			opacity 160ms ease,
			transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
	}

	.plus-overlay {
		opacity: 0;
		transform: scale(0.85);
	}

	.circle-icon,
	.check-icon {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		transition:
			opacity 160ms ease,
			transform 160ms cubic-bezier(0.2, 0.8, 0.2, 1);
	}

	.circle-icon {
		opacity: 1;
		transform: scale(1);
	}

	.check-icon {
		opacity: 0;
		transform: scale(0.75) rotate(-12deg);
	}

	.morph-plus.is-incoming .plus-overlay {
		animation: nokodo-plus-to-circle-plus 200ms ease var(--reminder-motion-delay-ms, 0ms)
			forwards;
	}

	.morph-plus.is-incoming .circle-icon {
		animation: nokodo-plus-to-circle-circle 200ms ease var(--reminder-motion-delay-ms, 0ms)
			forwards;
	}

	.morph-plus.is-incoming .check-icon {
		opacity: 0;
	}

	.circle-btn:hover .circle-icon {
		opacity: 0;
		transform: scale(0.9);
	}

	.circle-btn:hover .check-icon {
		opacity: 1;
		transform: scale(1) rotate(0deg);
	}

	.opacity-65 .circle-btn .circle-icon {
		opacity: 0;
	}

	.opacity-65 .circle-btn .check-icon {
		opacity: 1;
		transform: scale(1);
	}

	@keyframes nokodo-plus-to-circle-plus {
		from {
			opacity: 1;
			transform: scale(1);
		}
		to {
			opacity: 0;
			transform: scale(0.85);
		}
	}

	@keyframes nokodo-plus-to-circle-circle {
		from {
			opacity: 0;
			transform: scale(0.85);
		}
		to {
			opacity: 1;
			transform: scale(1);
		}
	}

	.title-text {
		position: relative;
		display: inline-block;
		max-width: 100%;
	}

	.title-overlay {
		position: absolute;
		left: 0;
		top: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		opacity: 0;
		pointer-events: none;
	}

	.title-text::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		top: 50%;
		height: 2px;
		background: rgba(255, 255, 255, 0.68);
		transform: scaleX(0);
		transform-origin: left;
		pointer-events: none;
	}

	.is-completed .title-text::after {
		transform: scaleX(1);
	}

	.is-incoming {
		pointer-events: none;
		max-height: 0px;
		opacity: 0;
		animation: nokodo-reminder-in 200ms ease var(--reminder-motion-delay-ms, 0ms) forwards;
	}

	.is-out {
		pointer-events: none;
		animation: nokodo-reminder-out 420ms ease 0ms forwards;
	}

	.is-out-complete .title-text::after {
		animation: nokodo-reminder-strike-in 420ms ease forwards;
	}

	.is-out-uncomplete .title-text::after {
		animation: nokodo-reminder-strike-out 420ms ease forwards;
	}

	@keyframes nokodo-reminder-strike-in {
		0% {
			transform: scaleX(0);
		}
		40% {
			transform: scaleX(1);
		}
		100% {
			transform: scaleX(1);
		}
	}

	@keyframes nokodo-reminder-strike-out {
		0% {
			transform: scaleX(1);
		}
		40% {
			transform: scaleX(0);
		}
		100% {
			transform: scaleX(0);
		}
	}

	@keyframes nokodo-reminder-out {
		0% {
			opacity: 1;
			max-height: 360px;
		}
		55% {
			opacity: 1;
			max-height: 360px;
		}
		100% {
			opacity: 0;
			max-height: 0px;
		}
	}

	@keyframes nokodo-reminder-in {
		from {
			opacity: 0;
			max-height: 0px;
		}
		to {
			opacity: 1;
			max-height: 360px;
		}
	}
</style>
