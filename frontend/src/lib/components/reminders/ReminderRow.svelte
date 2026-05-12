<script lang="ts">
	import DeleteButton from '$lib/components/DeleteButton.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import Bell from '$lib/components/icons/Bell.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import Circle from '$lib/components/icons/Circle.svelte'
	import ClockRotateRight from '$lib/components/icons/ClockRotateRight.svelte'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import ListBullet from '$lib/components/icons/ListBullet.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { MenuItem, PopupMenu } from '$lib/components/primitives'
	import RecurrenceEditor from '$lib/components/scheduling/RecurrenceEditor.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type {
		ReminderListWithCounts,
		ReminderUpdate,
		ReminderWithSubtasks,
	} from '$lib/stores/reminders.svelte'
	import { describeRecurrence, type Recurrence } from '$lib/utils/recurrence'
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
		onUpdate: (updates: ReminderUpdate) => void | Promise<void>
		availableLists: ReminderListWithCounts[]
		motion?: Motion
		motionDelayMs?: number
		editable?: boolean
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
	let menuButtonEl: HTMLButtonElement | null = $state(null)
	let titleInputEl: HTMLInputElement | null = $state(null)
	let dateButtonEl: HTMLButtonElement | null = $state(null)
	let repeatButtonEl: HTMLButtonElement | null = $state(null)

	let isMenuOpen = $state(false)
	let isDatePickerOpen = $state(false)
	let isRepeatMenuOpen = $state(false)

	const DESCRIPTION_PREVIEW_MAX = 140

	let editedTitle = $state('')
	let editedDescription = $state('')

	const isCompleted = $derived(props.kind === 'edit' && props.reminder.status === 'completed')
	const isEditable = $derived(props.kind === 'create' || (props.editable ?? true))
	const isMotionIn = $derived(props.motion === 'in')
	const isMotionOutComplete = $derived(props.motion === 'out-complete')
	const isMotionOutUncomplete = $derived(props.motion === 'out-uncomplete')
	const isMorphPlus = $derived(props.kind === 'edit' && props.iconMorph === 'plus-to-circle')
	const hasDueDate = $derived(props.kind === 'edit' && props.reminder.due_at != null)
	const hasRemindAt = $derived(props.kind === 'edit' && props.reminder.remind_at != null)
	const formattedDueDate = $derived.by(() => {
		if (props.kind !== 'edit') return null
		if (!props.reminder.due_at) return null
		return formatScheduleDateTime(props.reminder.due_at)
	})
	const formattedRemindAt = $derived.by(() => {
		if (props.kind !== 'edit') return null
		if (!props.reminder.remind_at) return null
		return formatScheduleDateTime(props.reminder.remind_at)
	})
	const descriptionPreview = $derived.by(() => {
		if (props.kind !== 'edit') return null
		return truncateText(props.reminder.description, DESCRIPTION_PREVIEW_MAX)
	})

	function formatScheduleDateTime(iso: string): string {
		const date = new SvelteDate(iso)
		const now = new SvelteDate()
		const isToday = date.toDateString() === now.toDateString()
		const tomorrow = new SvelteDate(now)
		tomorrow.setDate(tomorrow.getDate() + 1)
		const isTomorrow = date.toDateString() === tomorrow.toDateString()

		const time = date
			.toLocaleTimeString(undefined, {
				hour: 'numeric',
				minute: '2-digit',
			})
			.toLowerCase()

		if (isToday) return `today ${time}`
		if (isTomorrow) return `tomorrow ${time}`

		const dateLabel = date
			.toLocaleDateString(undefined, {
				month: 'short',
				day: 'numeric',
			})
			.toLowerCase()
		return `${dateLabel} ${time}`
	}

	function truncateText(value: string | null | undefined, maxLength: number): string | null {
		const trimmed = value?.trim()
		if (!trimmed) return null
		if (trimmed.length <= maxLength) return trimmed
		return `${trimmed.slice(0, maxLength).trimEnd()}...`
	}

	const isOverdue = $derived.by(() => {
		if (props.kind !== 'edit') return false
		if (!props.reminder.due_at || props.reminder.status === 'completed') return false
		return new SvelteDate(props.reminder.due_at) < new SvelteDate()
	})

	const recurrenceLabel = $derived.by(() => {
		if (props.kind !== 'edit') return null
		if (!props.reminder.recurrence) return null
		return describeRecurrence(
			props.reminder.recurrence,
			props.reminder.due_at ?? props.reminder.remind_at ?? null
		)
	})
	const recurrenceAnchor = $derived.by(() => {
		if (props.kind !== 'edit') return null
		return props.reminder.due_at ?? props.reminder.remind_at ?? defaultDueAtIso()
	})

	/** convert an ISO datetime to the local-tz format used by datetime-local inputs. */
	function isoToLocalInput(iso: string | null | undefined): string {
		if (!iso) return ''
		const d = new SvelteDate(iso)
		if (Number.isNaN(d.getTime())) return ''
		// build YYYY-MM-DDTHH:mm in local time without converting to UTC.
		const pad = (n: number) => String(n).padStart(2, '0')
		return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
	}

	/** convert a datetime-local string back to a UTC ISO string for the API. */
	function localInputToIso(value: string): string | null {
		if (!value) return null
		const d = new SvelteDate(value)
		if (Number.isNaN(d.getTime())) return null
		return d.toISOString()
	}

	let dueDraft = $state('')

	$effect(() => {
		if (props.kind !== 'edit') return
		if (isDatePickerOpen) return // don't clobber while user is editing
		dueDraft = isoToLocalInput(props.reminder.due_at)
	})

	function handleDueChange(value: string) {
		if (props.kind !== 'edit' || !isEditable) return
		dueDraft = value
		const iso = localInputToIso(value)
		void props.onUpdate({ due_at: iso })
	}

	function setDuePreset(daysFromToday: number) {
		if (props.kind !== 'edit' || !isEditable) return
		const date = new SvelteDate()
		date.setDate(date.getDate() + daysFromToday)
		if (daysFromToday === 0) {
			date.setHours(date.getHours() + 1, 0, 0, 0)
		} else {
			date.setHours(9, 0, 0, 0)
		}
		dueDraft = isoToLocalInput(date.toISOString())
		void props.onUpdate({ due_at: date.toISOString() })
		isDatePickerOpen = false
	}

	function clearDue() {
		if (props.kind !== 'edit' || !isEditable) return
		dueDraft = ''
		void props.onUpdate({ due_at: null })
		isDatePickerOpen = false
	}

	function defaultDueAtIso(): string {
		const date = new SvelteDate()
		date.setHours(date.getHours() + 1, 0, 0, 0)
		return date.toISOString()
	}

	function handleRecurrenceChange(value: Recurrence | null) {
		if (props.kind !== 'edit' || !isEditable) return
		const updates: ReminderUpdate = { recurrence: value }
		if (value && !props.reminder.due_at && !props.reminder.remind_at) {
			const dueAt = defaultDueAtIso()
			updates.due_at = dueAt
			dueDraft = isoToLocalInput(dueAt)
		}
		void props.onUpdate(updates)
	}

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
			if (!isEditable) return
			props.onSelect()
			await focusTitle()
		}
	}

	function handleTitleBlur() {
		const trimmed = editedTitle.trim()

		if (props.kind === 'edit') {
			if (!isEditable) return
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
			if (!isEditable) return
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
		if (!isEditable) return
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
		if (props.kind !== 'edit' || !isEditable) return
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
	class="reminder-row group relative cursor-pointer overflow-visible rounded-4xl transition-colors duration-150 {props.expanded
		? 'border-foreground/14 bg-foreground/6 border'
		: 'hover:bg-foreground/6 border border-transparent'} {isCompleted
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
			class="circle-btn text-foreground/55 flex h-6 w-6 shrink-0 items-center justify-center transition-colors duration-150 {isEditable
				? 'cursor-pointer'
				: 'cursor-default'} {props.kind === 'edit'
				? isEditable
					? 'hover:text-foreground/80'
					: ''
				: ''} {isCompleted ? 'text-emerald-400' : ''}"
			disabled={props.kind === 'edit' && !isEditable}
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
					<Plus class="h-6 w-6" strokeWidth="2" />
				</span>
			{:else}
				<span class="plus-icon plus-overlay" aria-hidden="true">
					<Plus class="h-6 w-6" strokeWidth="2" />
				</span>
				<span class="circle-icon" aria-hidden="true">
					<Circle class="h-6 w-6" />
				</span>
				<span class="check-icon" aria-hidden="true">
					<Check class="h-6 w-6" strokeWidth="2" />
				</span>
			{/if}
		</button>

		<div class="min-w-0 flex-1">
			{#if props.expanded}
				<div class="relative min-w-0">
					<input
						bind:this={titleInputEl}
						type="text"
						class="title-input text-foreground/90 placeholder:text-foreground/40 m-0 w-full appearance-none border-0 bg-transparent p-0 text-[0.95rem] leading-6 outline-none {isCompleted
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
				<div class="text-foreground/90 min-w-0 text-[0.95rem] leading-6">
					<span class="title-text">
						{props.kind === 'edit' ? props.reminder.title : editedTitle}
					</span>
				</div>
			{/if}
		</div>

		{#if props.kind === 'edit' && isEditable}
			<div data-menu-area class="flex items-center">
				<button
					bind:this={menuButtonEl}
					type="button"
					class="rounded-circle text-foreground/70 hover:bg-foreground/10 hover:text-foreground flex h-9 w-9 cursor-pointer items-center justify-center transition-all duration-150 {device.isTouch ||
					!device.hasHover
						? 'opacity-100'
						: 'opacity-0 group-hover:opacity-100'}"
					onclick={(event) => {
						event.stopPropagation()
						isMenuOpen = !isMenuOpen
					}}
					aria-label="reminder actions"
				>
					<EllipsisHorizontal class="h-5 w-5" />
				</button>
			</div>
		{/if}
	</div>

	<div class="details-shell {props.expanded ? 'expanded' : ''}">
		<div class="details-inner">
			<div class="space-y-3 px-3 pt-1 pb-3">
				<textarea
					class="text-foreground/70 placeholder:text-foreground/35 w-full resize-none bg-transparent pl-9 text-sm leading-5 outline-none"
					placeholder="add details"
					rows="2"
					bind:value={editedDescription}
					onblur={handleDescriptionBlur}
					onkeydown={handleDescriptionKeyDown}
				></textarea>

				<div class="flex flex-wrap items-center gap-2 pl-9">
					{#if props.kind === 'edit'}
						<button
							bind:this={dateButtonEl}
							type="button"
							class="rounded-pill border-foreground/14 bg-foreground/4 hover:bg-foreground/8 flex cursor-pointer items-center gap-1.5 border px-3 py-1.5 text-xs transition-colors {hasDueDate
								? isOverdue
									? 'text-red-400'
									: 'text-foreground/70'
								: 'text-foreground/55'}"
							onclick={(event) => {
								event.stopPropagation()
								isDatePickerOpen = !isDatePickerOpen
							}}
						>
							<Calendar variant="solid" class="h-3.5 w-3.5" />
							<span>{hasDueDate ? formattedDueDate : 'add date/time'}</span>
						</button>

						<button
							bind:this={repeatButtonEl}
							type="button"
							class="rounded-pill border-foreground/14 bg-foreground/4 hover:bg-foreground/8 flex cursor-pointer items-center gap-1.5 border px-3 py-1.5 text-xs transition-colors {recurrenceLabel
								? 'text-foreground/70'
								: 'text-foreground/55'}"
							onclick={(event) => {
								event.stopPropagation()
								isRepeatMenuOpen = !isRepeatMenuOpen
							}}
						>
							<ArrowPath class="h-3.5 w-3.5" />
							<span>{recurrenceLabel ?? 'repeat'}</span>
						</button>
					{:else}
						<button
							type="button"
							class="rounded-pill border-foreground/14 bg-foreground/4 text-foreground/55 hover:bg-foreground/8 flex cursor-pointer items-center gap-1.5 border px-3 py-1.5 text-xs transition-colors"
							disabled
						>
							<Calendar variant="solid" class="h-3.5 w-3.5" />
							<span>add date/time</span>
						</button>

						<button
							type="button"
							class="rounded-pill border-foreground/14 bg-foreground/4 text-foreground/55 hover:bg-foreground/8 flex cursor-pointer items-center gap-1.5 border px-3 py-1.5 text-xs transition-colors"
							disabled
						>
							<ArrowPath class="h-3.5 w-3.5" />
							<span>repeat</span>
						</button>
					{/if}

					{#if props.kind === 'create'}
						<button
							type="button"
							class="rounded-pill border-foreground/14 bg-foreground/8 text-foreground/85 hover:bg-foreground/12 ml-auto cursor-pointer border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45"
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

	{#if props.kind === 'edit' && (descriptionPreview || hasDueDate || hasRemindAt || recurrenceLabel) && !props.expanded}
		<div class="min-w-0 px-3 pb-2 pl-12">
			{#if descriptionPreview}
				<p class="text-foreground/60 min-w-0 text-xs leading-5 wrap-break-word">
					{descriptionPreview}
				</p>
			{/if}

			{#if hasDueDate || hasRemindAt || recurrenceLabel}
				<div class="mt-1.5 flex min-w-0 flex-wrap items-center gap-1.5">
					{#if hasDueDate}
						<span
							class="rounded-pill border-foreground/10 bg-foreground/5 inline-flex min-w-0 items-center gap-1.5 border px-2 py-1 text-xs {isOverdue
								? 'text-red-400'
								: 'text-foreground/60'}"
						>
							<Calendar variant="solid" class="h-3.5 w-3.5 shrink-0" />
							{formattedDueDate}
						</span>
					{/if}
					{#if hasRemindAt}
						<span
							class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/60 inline-flex min-w-0 items-center gap-1.5 border px-2 py-1 text-xs"
						>
							<Bell class="h-3.5 w-3.5 shrink-0" />
							{formattedRemindAt}
						</span>
					{/if}
					{#if recurrenceLabel}
						<span
							class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/60 inline-flex min-w-0 items-center gap-1.5 border px-2 py-1 text-xs"
						>
							<ArrowPath class="h-3.5 w-3.5 shrink-0" />
							{recurrenceLabel}
						</span>
					{/if}
				</div>
			{/if}
		</div>
	{/if}

	{#if props.kind === 'edit'}
		<PopupMenu open={isMenuOpen} anchorEl={menuButtonEl} onClose={() => (isMenuOpen = false)}>
			<div
				class="text-foreground/50 flex items-center gap-2 px-3 pt-1 pb-2 text-xs font-semibold tracking-[0.08em] uppercase"
			>
				<ListBullet class="h-3.5 w-3.5" />
				move to
			</div>
			<div class="max-h-44 overflow-auto">
				{#each props.availableLists as list (list.id)}
					<MenuItem
						selected={props.reminder.list_id === list.id}
						onclick={(event) => {
							event.stopPropagation()
							isMenuOpen = false
							void props.onMove(list.id)
						}}
					>
						{#snippet icon()}
							<span
								class="rounded-pill flex h-4 w-4 items-center justify-center"
								style:background-color={list.color ?? 'rgba(255,255,255,0.1)'}
							>
								<span class="text-[0.55rem]">{list.icon ?? ''}</span>
							</span>
						{/snippet}
						{list.name}
					</MenuItem>
				{/each}
			</div>

			<div class="bg-foreground/10 my-1 h-px w-full"></div>
			<div class="mt-1">
				<DeleteButton
					confirm={true}
					stopPropagation={true}
					onTrigger={() => (isMenuOpen = false)}
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
		</PopupMenu>

		<PopupMenu
			open={isDatePickerOpen}
			anchorEl={dateButtonEl}
			onClose={() => (isDatePickerOpen = false)}
		>
			<div class="flex w-72 max-w-[calc(100vw-1rem)] flex-col gap-3 p-2">
				<div
					class="text-foreground/50 flex items-center gap-2 px-1 text-xs font-semibold tracking-[0.08em] uppercase"
				>
					<Calendar variant="solid" class="h-3.5 w-3.5" />
					schedule
				</div>
				<div class="grid grid-cols-3 gap-1">
					<button
						type="button"
						class="rounded-pill bg-foreground/6 text-foreground/75 hover:bg-foreground/10 flex cursor-pointer items-center justify-center gap-1.5 border-none px-2 py-1.5 text-xs transition-colors"
						onclick={(event) => {
							event.stopPropagation()
							setDuePreset(0)
						}}
					>
						<ClockRotateRight class="h-3.5 w-3.5" />
						today
					</button>
					<button
						type="button"
						class="rounded-pill bg-foreground/6 text-foreground/75 hover:bg-foreground/10 flex cursor-pointer items-center justify-center gap-1.5 border-none px-2 py-1.5 text-xs transition-colors"
						onclick={(event) => {
							event.stopPropagation()
							setDuePreset(1)
						}}
					>
						<Calendar class="h-3.5 w-3.5" />
						tomorrow
					</button>
					<button
						type="button"
						class="rounded-pill bg-foreground/6 text-foreground/75 hover:bg-foreground/10 flex cursor-pointer items-center justify-center gap-1.5 border-none px-2 py-1.5 text-xs transition-colors"
						onclick={(event) => {
							event.stopPropagation()
							setDuePreset(7)
						}}
					>
						<ArrowPath class="h-3.5 w-3.5" />
						next week
					</button>
				</div>
				<label class="text-foreground/55 px-1 text-xs font-medium" for="due-input">
					custom date and time
				</label>
				<input
					id="due-input"
					type="datetime-local"
					class="rounded-pill border-foreground/14 bg-foreground/5 text-foreground/85 focus:border-foreground/30 border px-3 py-2 text-sm transition-colors outline-none"
					value={dueDraft}
					onclick={(e) => e.stopPropagation()}
					oninput={(e) => handleDueChange((e.target as HTMLInputElement).value)}
				/>
				{#if hasDueDate}
					<MenuItem
						onclick={(event) => {
							event.stopPropagation()
							clearDue()
						}}
					>
						{#snippet icon()}<XMark class="h-4 w-4" />{/snippet}
						clear
					</MenuItem>
				{/if}
			</div>
		</PopupMenu>

		<PopupMenu
			open={isRepeatMenuOpen}
			anchorEl={repeatButtonEl}
			onClose={() => (isRepeatMenuOpen = false)}
			estimatedHeight={320}
			class="overflow-hidden"
		>
			<div class="w-[min(calc(100vw-3rem),20rem)] max-w-full">
				<div class="max-h-[min(70vh,26rem)] overflow-y-auto overscroll-contain p-1">
					<RecurrenceEditor
						value={props.reminder.recurrence ?? null}
						anchorDate={recurrenceAnchor}
						timezone={props.reminder.recurrence?.timezone ?? null}
						onChange={handleRecurrenceChange}
					/>
				</div>
			</div>
		</PopupMenu>
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
		display: inline;
		max-width: 100%;
		overflow-wrap: anywhere;
		word-break: break-word;
	}

	.title-overlay {
		position: absolute;
		display: inline-block;
		left: 0;
		top: 0;
		max-width: 100%;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		opacity: 0;
		pointer-events: none;
	}

	.title-text::after {
		display: none;
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

	.is-completed .title-text {
		text-decoration-line: line-through;
		text-decoration-thickness: 2px;
		text-decoration-color: rgba(255, 255, 255, 0.68);
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
