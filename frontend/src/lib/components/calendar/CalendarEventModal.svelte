<script lang="ts">
	import TagEditor from '$lib/components/common/TagEditor.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Bell from '$lib/components/icons/Bell.svelte'
	import Calendar from '$lib/components/icons/Calendar.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ClockRotateRight from '$lib/components/icons/ClockRotateRight.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Info from '$lib/components/icons/Info.svelte'
	import Link from '$lib/components/icons/Link.svelte'
	import Map from '$lib/components/icons/Map.svelte'
	import Tag from '$lib/components/icons/Tag.svelte'
	import Trash from '$lib/components/icons/Trash.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import { Switch } from '$lib/components/primitives'
	import NotificationOffsetsEditor from '$lib/components/scheduling/NotificationOffsetsEditor.svelte'
	import RecurrenceEditor from '$lib/components/scheduling/RecurrenceEditor.svelte'
	import {
		calendarEvents,
		calendars,
		type CalendarEvent,
		type CalendarEventCreate,
		type CalendarEventUpdate,
	} from '$lib/stores/calendars.svelte'
	import { modals } from '$lib/stores/modals.svelte'
	import { canEditAccessLevel, resourceAccess } from '$lib/stores/resourceAccess.svelte'
	import { describeNotificationOffsets, describeRecurrence } from '$lib/utils/recurrence'
	import { SvelteDate } from 'svelte/reactivity'

	interface Props {
		open: boolean
		defaultStart: Date
		defaultCalendarId?: string | null
		event?: CalendarEvent | null
		onClose: () => void
		onSaved?: (event: CalendarEvent) => void | Promise<void>
		onDeleted?: (eventId: string) => void | Promise<void>
	}

	type PlaceMode = 'location' | 'virtual'
	type EventRecurrence = NonNullable<CalendarEventCreate['recurrence']>

	const panelClass =
		'border-foreground/13 bg-background/70 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)] backdrop-blur-[16px] backdrop-saturate-[1.08]'
	const fieldClass = `${panelClass} grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-2 rounded-[16px] border p-3`
	const inputClass =
		'border-foreground/12 bg-foreground/4 text-foreground/90 placeholder:text-foreground/35 min-h-10 w-full min-w-0 rounded-xl border px-3 py-2 outline-none transition-colors duration-150 focus:border-[color-mix(in_oklch,var(--accent-primary)_48%,transparent)] focus:bg-foreground/6 disabled:cursor-not-allowed disabled:opacity-55'
	const fieldIconClass = 'h-4 w-4 text-(--accent-primary)'
	const fieldLabelClass = 'text-foreground/60 text-[0.78rem] font-semibold'
	const pillButtonClass =
		'rounded-pill inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 border-none px-3 text-[0.78rem] font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const activePillClass =
		'bg-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] text-foreground'
	const optionButtonClass =
		'rounded-pill inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 border px-3 text-[0.78rem] font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const optionButtonActiveClass =
		'border-[color-mix(in_oklch,var(--accent-primary)_36%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_20%,transparent)] text-foreground'
	const optionButtonQuietClass =
		'border-foreground/10 bg-foreground/5 text-foreground/72 hover:bg-foreground/8 hover:text-foreground'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

	let {
		open,
		defaultStart,
		defaultCalendarId = null,
		event = null,
		onClose,
		onSaved,
		onDeleted,
	}: Props = $props()

	let title = $state('')
	let description = $state('')
	let startDate = $state('')
	let endDate = $state('')
	let startTime = $state('')
	let endTime = $state('')
	let allDay = $state(false)
	let selectedCalendarId = $state('')
	let timezone = $state('')
	let placeMode = $state<PlaceMode>('location')
	let location = $state('')
	let virtualUrl = $state('')
	let recurrenceValue = $state<EventRecurrence | null>(null)
	let labels = $state<string[]>([])
	let notificationOffsets = $state<number[]>([10])
	let showNotifications = $state(false)
	let showRepeat = $state(false)
	let showWhere = $state(false)
	let showDetails = $state(false)
	let showTimezone = $state(false)
	let error = $state('')
	let saving = $state(false)

	const availableCalendars = $derived(calendars.all)
	const selectedCalendar = $derived(
		availableCalendars.find((calendar) => calendar.id === selectedCalendarId) ?? null
	)
	const selectedCalendarAccessLevel = $derived(
		selectedCalendar
			? resourceAccess.level('calendar', selectedCalendar.id, selectedCalendar.owner_id)
			: null
	)
	const canEditEvent = $derived(canEditAccessLevel(selectedCalendarAccessLevel))
	const isExisting = $derived(Boolean(event?.id))
	const modalTitle = $derived(isExisting ? 'event details' : 'create event')
	const previewDate = $derived(formatPreviewDate(startDate, endDate, allDay))
	const previewTime = $derived(formatPreviewTime())
	const recurrenceAnchor = $derived(
		allDay ? toIsoString(startDate, '00:00') : toIsoString(startDate, startTime)
	)
	const notificationSummary = $derived(describeNotificationOffsets(notificationOffsets))
	const recurrenceSummary = $derived(describeRecurrence(recurrenceValue, recurrenceAnchor))
	const whereSummary = $derived(
		placeMode === 'virtual' ? virtualUrl.trim() || 'link' : location.trim() || 'place'
	)
	const detailsSummary = $derived(
		description.trim() || labels.length > 0 ? 'details added' : 'details'
	)
	const timezoneSummary = $derived(timezone.trim() || 'local timezone')
	const activeCalendarName = $derived(
		availableCalendars.find((calendar) => calendar.id === selectedCalendarId)?.name ??
			'calendar'
	)

	$effect(() => {
		if (!open) return
		for (const calendar of availableCalendars) {
			void resourceAccess.ensure('calendar', calendar.id, calendar.owner_id)
		}
	})

	$effect(() => {
		if (!open) return
		if (event) {
			hydrateExisting(event)
			return
		}
		hydrateNew(defaultStart)
	})

	function pad(value: number): string {
		return String(value).padStart(2, '0')
	}

	function toDateValue(date: Date): string {
		return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
	}

	function toTimeValue(date: Date): string {
		return `${pad(date.getHours())}:${pad(date.getMinutes())}`
	}

	function addDays(dateValue: string, days: number): string {
		const timestamp = Date.parse(`${dateValue}T00:00`)
		if (Number.isNaN(timestamp)) return dateValue
		const date = new SvelteDate(timestamp)
		date.setDate(date.getDate() + days)
		return toDateValue(date)
	}

	function displayAllDayEnd(endAt: string): string {
		const end = new SvelteDate(endAt)
		if (Number.isNaN(end.getTime())) return ''
		return toDateValue(new SvelteDate(Math.max(0, end.getTime() - 1)))
	}

	function toIsoString(dateValue: string, timeValue: string): string | null {
		const timestamp = Date.parse(`${dateValue}T${timeValue}`)
		if (Number.isNaN(timestamp)) return null
		return new SvelteDate(timestamp).toISOString()
	}

	function hydrateNew(startValue: Date): void {
		const start = new SvelteDate(startValue)
		const end = new SvelteDate(start.getTime() + 60 * 60 * 1000)
		title = ''
		description = ''
		startDate = toDateValue(start)
		endDate = toDateValue(end)
		startTime = toTimeValue(start)
		endTime = toTimeValue(end)
		allDay = false
		selectedCalendarId = defaultCalendarId ?? calendars.defaultCalendar?.id ?? ''
		timezone = localTimezone
		placeMode = 'location'
		location = ''
		virtualUrl = ''
		recurrenceValue = null
		labels = []
		notificationOffsets = [10]
		showNotifications = true
		showRepeat = false
		showWhere = false
		showDetails = false
		showTimezone = false
		error = ''
		saving = false
	}

	function hydrateExisting(source: CalendarEvent): void {
		const start = new SvelteDate(source.start_at)
		const end = new SvelteDate(source.end_at)
		const sourceDescription = source.description ?? ''
		const sourceLocation = source.location ?? ''
		const sourceVirtualUrl = source.virtual_url ?? ''
		const sourceLabels = [...(source.labels ?? [])]
		const sourceNotificationOffsets = [...(source.notification_offsets ?? [])]
		const sourceTimezone = source.timezone ?? localTimezone
		title = source.title
		description = sourceDescription
		startDate = toDateValue(start)
		endDate = source.all_day ? displayAllDayEnd(source.end_at) : toDateValue(end)
		startTime = toTimeValue(start)
		endTime = toTimeValue(end)
		allDay = source.all_day
		selectedCalendarId = source.calendar_id
		timezone = sourceTimezone
		placeMode = source.virtual_url ? 'virtual' : 'location'
		location = sourceLocation
		virtualUrl = sourceVirtualUrl
		recurrenceValue = source.recurrence ?? null
		labels = sourceLabels
		notificationOffsets = sourceNotificationOffsets
		showNotifications = sourceNotificationOffsets.length > 0
		showRepeat = Boolean(source.recurrence)
		showWhere = Boolean(sourceLocation || sourceVirtualUrl)
		showDetails = Boolean(sourceDescription || sourceLabels.length > 0)
		showTimezone = Boolean(source.timezone && source.timezone !== localTimezone)
		error = ''
		saving = false
	}

	function selectPlaceMode(mode: PlaceMode): void {
		if (!canEditEvent) return
		placeMode = mode
		if (mode === 'location') {
			virtualUrl = ''
			return
		}
		location = ''
	}

	function formatPreviewDate(start: string, end: string, isAllDay: boolean): string {
		const startTimestamp = Date.parse(`${start}T00:00`)
		if (Number.isNaN(startTimestamp)) return 'event'
		const formatter = new Intl.DateTimeFormat(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
		})
		const startLabel = formatter.format(new SvelteDate(startTimestamp)).toLowerCase()
		if (!isAllDay || !end || end === start) return startLabel
		const endTimestamp = Date.parse(`${end}T00:00`)
		if (Number.isNaN(endTimestamp)) return startLabel
		return `${startLabel} - ${formatter.format(new SvelteDate(endTimestamp)).toLowerCase()}`
	}

	function formatPreviewTime(): string {
		if (allDay) return 'all day'
		const startAt = toIsoString(startDate, startTime)
		const endAt = toIsoString(endDate, endTime)
		if (!startAt || !endAt) return 'pick a time'
		const formatter = new Intl.DateTimeFormat(undefined, {
			hour: 'numeric',
			minute: '2-digit',
		})
		return `${formatter.format(new SvelteDate(startAt)).toLowerCase()} - ${formatter
			.format(new SvelteDate(endAt))
			.toLowerCase()}`
	}

	function buildDateRange(): { startAt: string; endAt: string } | null {
		if (allDay) {
			const startAt = toIsoString(startDate, '00:00')
			const endAt = toIsoString(addDays(endDate || startDate, 1), '00:00')
			if (!startAt || !endAt) return null
			return { startAt, endAt }
		}

		const startAt = toIsoString(startDate, startTime)
		const endAt = toIsoString(endDate, endTime)
		if (!startAt || !endAt) return null
		return { startAt, endAt }
	}

	function buildPayload(): CalendarEventCreate | CalendarEventUpdate | null {
		const trimmedTitle = title.trim()
		const range = buildDateRange()
		if (!trimmedTitle) {
			error = 'title is required'
			return null
		}
		if (!selectedCalendarId) {
			error = 'calendar is required'
			return null
		}
		if (!range) {
			error = 'date is required'
			return null
		}
		if (Date.parse(range.endAt) <= Date.parse(range.startAt)) {
			error = 'end must be after start'
			return null
		}

		return {
			title: trimmedTitle,
			description: description.trim() || null,
			start_at: range.startAt,
			end_at: range.endAt,
			all_day: allDay,
			timezone: timezone.trim() || null,
			recurrence: recurrenceValue
				? {
						...recurrenceValue,
						timezone: timezone.trim() || recurrenceValue.timezone || null,
					}
				: null,
			notification_offsets: notificationOffsets,
			location: placeMode === 'location' ? location.trim() || null : null,
			virtual_url: placeMode === 'virtual' ? virtualUrl.trim() || null : null,
			labels,
			metadata_: event?.metadata_ ?? {},
		}
	}

	function handleSubmit(formEvent: SubmitEvent): void {
		formEvent.preventDefault()
		void save()
	}

	async function save(): Promise<void> {
		if (saving || !canEditEvent) return
		const payload = buildPayload()
		if (!payload) return
		saving = true
		error = ''
		try {
			const saved = event?.id
				? await calendarEvents.update(event.id, payload as CalendarEventUpdate)
				: await calendarEvents.create(selectedCalendarId, payload as CalendarEventCreate)
			if (!saved) return
			onClose()
			await onSaved?.(saved)
		} finally {
			saving = false
		}
	}

	function requestDelete(): void {
		if (!event?.id || !canEditEvent) return
		modals.open('confirm-delete', {
			title: 'delete event?',
			description: event.title,
			onDelete: async () => {
				const deleted = await calendarEvents.remove(event.id)
				if (!deleted) return false
				onClose()
				await onDeleted?.(event.id)
				return true
			},
		})
	}
</script>

<BaseModal
	{open}
	title={modalTitle}
	description={`${previewDate} · ${activeCalendarName}`}
	onClose={() => !saving && onClose()}
	widthClassName="max-w-3xl"
>
	<form class="grid grid-cols-2 gap-3 max-[680px]:grid-cols-1" onsubmit={handleSubmit}>
		<section
			class="{panelClass} col-span-full flex min-w-0 items-center gap-4 rounded-[18px] border p-4 max-[680px]:flex-wrap max-[680px]:items-start"
		>
			<div
				class="flex h-11 w-11 shrink-0 items-center justify-center rounded-[15px] border border-[color-mix(in_oklch,var(--accent-primary)_22%,transparent)] bg-[color-mix(in_oklch,var(--accent-primary)_12%,transparent)] text-(--accent-primary)"
			>
				<Calendar class="h-5 w-5" />
			</div>
			<div class="min-w-0 flex-1">
				<p class="text-foreground/50 text-xs font-medium tracking-[0.12em] uppercase">
					{previewTime}
				</p>
				<h3 class="text-foreground min-w-0 truncate text-lg font-semibold">
					{title.trim() || 'untitled event'}
				</h3>
			</div>
			<div
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/75 ml-auto inline-flex items-center gap-2 border px-3 py-2 text-[0.8rem] font-semibold whitespace-nowrap max-[680px]:ml-auto"
			>
				<span>all day</span>
				<Switch
					size="sm"
					bind:checked={allDay}
					disabled={saving || !canEditEvent}
					ariaLabel="all day"
				/>
			</div>
		</section>

		<div class="{fieldClass} col-span-full">
			<Info class={fieldIconClass} />
			<label class={fieldLabelClass} for="calendar-event-title">title</label>
			<input
				id="calendar-event-title"
				type="text"
				bind:value={title}
				class="{inputClass} col-span-full text-base"
				placeholder="event title"
				disabled={saving || !canEditEvent}
			/>
		</div>

		<div class="col-span-full grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
			<div class={fieldClass}>
				<ClockRotateRight class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-start-date">starts</label>
				<div
					class="col-span-full grid min-w-0 gap-2 {allDay
						? 'grid-cols-1'
						: 'grid-cols-[minmax(0,1fr)_minmax(7rem,8.5rem)] max-[680px]:grid-cols-1'}"
				>
					<input
						id="calendar-event-start-date"
						type="date"
						bind:value={startDate}
						class={inputClass}
						disabled={saving || !canEditEvent}
					/>
					{#if !allDay}
						<input
							type="time"
							bind:value={startTime}
							class={inputClass}
							disabled={saving || !canEditEvent}
							aria-label="start time"
						/>
					{/if}
				</div>
			</div>
			<div class={fieldClass}>
				<ClockRotateRight class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-end-date">ends</label>
				<div
					class="col-span-full grid min-w-0 gap-2 {allDay
						? 'grid-cols-1'
						: 'grid-cols-[minmax(0,1fr)_minmax(7rem,8.5rem)] max-[680px]:grid-cols-1'}"
				>
					<input
						id="calendar-event-end-date"
						type="date"
						bind:value={endDate}
						class={inputClass}
						disabled={saving || !canEditEvent}
					/>
					{#if !allDay}
						<input
							type="time"
							bind:value={endTime}
							class={inputClass}
							disabled={saving || !canEditEvent}
							aria-label="end time"
						/>
					{/if}
				</div>
			</div>
		</div>

		<div class="col-span-full grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
			<div class="{fieldClass} {showTimezone ? '' : 'col-span-full'}">
				<Calendar class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-calendar">calendar</label>
				<select
					id="calendar-event-calendar"
					bind:value={selectedCalendarId}
					class="{inputClass} col-span-full"
					disabled={saving || isExisting || availableCalendars.length === 0}
				>
					{#each availableCalendars as calendar (calendar.id)}
						<option value={calendar.id}>{calendar.name}</option>
					{/each}
				</select>
			</div>
			{#if showTimezone}
				<div class={fieldClass}>
					<GlobeAlt class={fieldIconClass} />
					<label class={fieldLabelClass} for="calendar-event-timezone">timezone</label>
					<input
						id="calendar-event-timezone"
						type="text"
						bind:value={timezone}
						class="{inputClass} col-span-full"
						placeholder="local timezone"
						disabled={saving || !canEditEvent}
					/>
				</div>
			{/if}
		</div>

		<section class="{panelClass} col-span-full rounded-2xl border p-2">
			<div class="flex flex-wrap gap-2">
				<button
					type="button"
					class="{optionButtonClass} {showNotifications
						? optionButtonActiveClass
						: optionButtonQuietClass}"
					disabled={saving || !canEditEvent}
					aria-pressed={showNotifications}
					onclick={() => (showNotifications = !showNotifications)}
				>
					<Bell class="h-4 w-4" />
					<span>notify</span>
					<span class="text-foreground/55 max-[520px]:hidden">{notificationSummary}</span>
				</button>
				<button
					type="button"
					class="{optionButtonClass} {showRepeat
						? optionButtonActiveClass
						: optionButtonQuietClass}"
					disabled={saving || !canEditEvent}
					aria-pressed={showRepeat}
					onclick={() => (showRepeat = !showRepeat)}
				>
					<ClockRotateRight class="h-4 w-4" />
					<span>repeat</span>
					<span class="text-foreground/55 max-[520px]:hidden">{recurrenceSummary}</span>
				</button>
				<button
					type="button"
					class="{optionButtonClass} {showWhere
						? optionButtonActiveClass
						: optionButtonQuietClass}"
					disabled={saving || !canEditEvent}
					aria-pressed={showWhere}
					onclick={() => (showWhere = !showWhere)}
				>
					{#if placeMode === 'virtual'}
						<Link class="h-4 w-4" />
					{:else}
						<Map class="h-4 w-4" />
					{/if}
					<span>where</span>
					<span class="text-foreground/55 max-[520px]:hidden">{whereSummary}</span>
				</button>
				<button
					type="button"
					class="{optionButtonClass} {showDetails
						? optionButtonActiveClass
						: optionButtonQuietClass}"
					disabled={saving || !canEditEvent}
					aria-pressed={showDetails}
					onclick={() => (showDetails = !showDetails)}
				>
					<Info class="h-4 w-4" />
					<span>{detailsSummary}</span>
				</button>
				<button
					type="button"
					class="{optionButtonClass} {showTimezone
						? optionButtonActiveClass
						: optionButtonQuietClass}"
					disabled={saving || !canEditEvent}
					aria-pressed={showTimezone}
					onclick={() => (showTimezone = !showTimezone)}
				>
					<GlobeAlt class="h-4 w-4" />
					<span>timezone</span>
					<span class="text-foreground/55 max-[520px]:hidden">{timezoneSummary}</span>
				</button>
			</div>
		</section>

		{#if showNotifications}
			<div class="{fieldClass} col-span-full">
				<Bell class={fieldIconClass} />
				<span class={fieldLabelClass}>notifications</span>
				<div class="col-span-full">
					<NotificationOffsetsEditor
						value={notificationOffsets}
						disabled={saving || !canEditEvent}
						onChange={(next) => (notificationOffsets = next)}
					/>
				</div>
			</div>
		{/if}

		{#if showRepeat}
			<div class="{fieldClass} col-span-full">
				<ClockRotateRight class={fieldIconClass} />
				<span class={fieldLabelClass}>repeat</span>
				<div class="col-span-full">
					<RecurrenceEditor
						value={recurrenceValue}
						anchorDate={recurrenceAnchor}
						{timezone}
						disabled={saving || !canEditEvent}
						onChange={(next) => (recurrenceValue = next)}
					/>
				</div>
			</div>
		{/if}

		{#if showWhere}
			<div class="{fieldClass} col-span-full">
				{#if placeMode === 'location'}
					<Map class={fieldIconClass} />
				{:else}
					<Link class={fieldIconClass} />
				{/if}
				<span class={fieldLabelClass}>where</span>
				<div
					class="col-span-full grid min-w-0 grid-cols-[auto_minmax(0,1fr)] gap-2 max-[680px]:grid-cols-1"
				>
					<div
						class="border-foreground/10 bg-foreground/5 rounded-pill flex flex-nowrap gap-1 border p-1"
						aria-label="event place mode"
					>
						<button
							type="button"
							class="{pillButtonClass} {placeMode === 'location'
								? activePillClass
								: 'text-foreground/70 hover:bg-foreground/8 hover:text-foreground bg-transparent'}"
							disabled={saving || !canEditEvent}
							onclick={() => selectPlaceMode('location')}
						>
							<Map class="h-4 w-4" />
							<span>place</span>
						</button>
						<button
							type="button"
							class="{pillButtonClass} {placeMode === 'virtual'
								? activePillClass
								: 'text-foreground/70 hover:bg-foreground/8 hover:text-foreground bg-transparent'}"
							disabled={saving || !canEditEvent}
							onclick={() => selectPlaceMode('virtual')}
						>
							<Link class="h-4 w-4" />
							<span>link</span>
						</button>
					</div>
					{#if placeMode === 'location'}
						<input
							type="text"
							bind:value={location}
							class={inputClass}
							placeholder="place or room"
							disabled={saving || !canEditEvent}
							aria-label="location"
						/>
					{:else}
						<input
							type="url"
							bind:value={virtualUrl}
							class={inputClass}
							placeholder="https://"
							disabled={saving || !canEditEvent}
							aria-label="virtual link"
						/>
					{/if}
				</div>
			</div>
		{/if}

		{#if showDetails}
			<div class="{fieldClass} col-span-full">
				<Info class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-description">description</label>
				<textarea
					id="calendar-event-description"
					bind:value={description}
					class="{inputClass} col-span-full min-h-24 resize-y text-sm"
					placeholder="details, notes, agenda"
					disabled={saving || !canEditEvent}
				></textarea>
			</div>
			<div class="{fieldClass} col-span-full">
				<Tag class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-labels">labels</label>
				<TagEditor
					inputId="calendar-event-labels"
					bind:value={labels}
					disabled={saving || !canEditEvent}
				/>
			</div>
		{/if}

		{#if error}
			<div class="text-destructive col-span-full text-sm">{error}</div>
		{/if}

		<div class="col-span-full flex items-center gap-2 pt-1 max-[680px]:flex-wrap">
			{#if event?.id && canEditEvent}
				<button
					type="button"
					class="{actionButtonClass} border border-red-500/30 bg-red-500/13 text-red-300"
					disabled={saving}
					onclick={requestDelete}
				>
					<Trash class="h-4 w-4" />
					<span>delete</span>
				</button>
			{/if}
			<div class="flex-1"></div>
			{#if canEditEvent}
				<button
					type="submit"
					class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
					disabled={saving || !title.trim()}
				>
					<Check class="h-4 w-4" />
					{#if saving}<ShimmerText className="inline-block">saving</ShimmerText
						>{:else}<span>save</span>{/if}
				</button>
			{/if}
		</div>
	</form>
</BaseModal>
