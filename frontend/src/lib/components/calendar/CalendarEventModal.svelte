<script lang="ts">
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
	import XMark from '$lib/components/icons/XMark.svelte'
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import {
		calendarEvents,
		calendars,
		type CalendarEvent,
		type CalendarEventCreate,
		type CalendarEventUpdate,
	} from '$lib/stores/calendars.svelte'
	import { modals } from '$lib/stores/modals.svelte'
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

	const notificationOptions = [
		{ label: 'start', value: 0 },
		{ label: '5 min', value: 5 },
		{ label: '10 min', value: 10 },
		{ label: '30 min', value: 30 },
		{ label: '1 hour', value: 60 },
		{ label: '1 day', value: 1440 },
	]

	const recurrenceOptions = [
		{ label: 'does not repeat', value: '' },
		{ label: 'daily', value: 'FREQ=DAILY' },
		{ label: 'weekly', value: 'FREQ=WEEKLY' },
		{ label: 'monthly', value: 'FREQ=MONTHLY' },
		{ label: 'yearly', value: 'FREQ=YEARLY' },
	]

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
	const quietPillClass =
		'bg-foreground/6 text-foreground/70 hover:bg-foreground/8 hover:text-foreground'
	const actionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'

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
	let recurrence = $state('')
	let labels = $state('')
	let notificationOffsets = $state<number[]>([10])
	let error = $state('')
	let saving = $state(false)

	const availableCalendars = $derived(calendars.all)
	const isExisting = $derived(Boolean(event?.id))
	const modalTitle = $derived(isExisting ? 'event details' : 'create event')
	const previewDate = $derived(formatPreviewDate(startDate, endDate, allDay))
	const previewTime = $derived(formatPreviewTime())
	const activeCalendarName = $derived(
		availableCalendars.find((calendar) => calendar.id === selectedCalendarId)?.name ??
			'calendar'
	)

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
		timezone = Intl.DateTimeFormat().resolvedOptions().timeZone
		placeMode = 'location'
		location = ''
		virtualUrl = ''
		recurrence = ''
		labels = ''
		notificationOffsets = [10]
		error = ''
		saving = false
	}

	function hydrateExisting(source: CalendarEvent): void {
		const start = new SvelteDate(source.start_at)
		const end = new SvelteDate(source.end_at)
		title = source.title
		description = source.description ?? ''
		startDate = toDateValue(start)
		endDate = source.all_day ? displayAllDayEnd(source.end_at) : toDateValue(end)
		startTime = toTimeValue(start)
		endTime = toTimeValue(end)
		allDay = source.all_day
		selectedCalendarId = source.calendar_id
		timezone = source.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
		placeMode = source.virtual_url ? 'virtual' : 'location'
		location = source.location ?? ''
		virtualUrl = source.virtual_url ?? ''
		recurrence = source.recurrence?.rrule?.[0] ?? ''
		labels = (source.labels ?? []).join(', ')
		notificationOffsets = [...(source.notification_offsets ?? [])]
		error = ''
		saving = false
	}

	function parseLabels(value: string): string[] {
		return [
			...new Set(
				value
					.split(',')
					.map((label) => label.trim())
					.filter(Boolean)
			),
		]
	}

	function selectPlaceMode(mode: PlaceMode): void {
		placeMode = mode
		if (mode === 'location') {
			virtualUrl = ''
			return
		}
		location = ''
	}

	function toggleNotificationOffset(value: number): void {
		if (notificationOffsets.includes(value)) {
			notificationOffsets = notificationOffsets.filter((offset) => offset !== value)
			return
		}
		notificationOffsets = [...notificationOffsets, value].toSorted((a, b) => a - b)
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

	function buildRecurrencePayload(): EventRecurrence | null {
		const rule = recurrence.trim()
		if (!rule) return null
		return {
			rrule: [rule],
			rdate: [],
			exdate: [],
			timezone: timezone.trim() || null,
		}
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
			recurrence: buildRecurrencePayload(),
			notification_offsets: notificationOffsets,
			location: placeMode === 'location' ? location.trim() || null : null,
			virtual_url: placeMode === 'virtual' ? virtualUrl.trim() || null : null,
			labels: parseLabels(labels),
			metadata_: event?.metadata_ ?? {},
		}
	}

	function handleSubmit(formEvent: SubmitEvent): void {
		formEvent.preventDefault()
		void save()
	}

	async function save(): Promise<void> {
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
		if (!event?.id) return
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
	description={`${previewDate} - ${activeCalendarName}`}
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
			<label
				class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/75 ml-auto inline-flex items-center gap-2 border px-3 py-2 text-[0.8rem] font-semibold whitespace-nowrap max-[680px]:ml-auto"
			>
				<input
					class="accent-(--accent-primary)"
					type="checkbox"
					bind:checked={allDay}
					disabled={saving}
				/>
				<span>all day</span>
			</label>
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
				disabled={saving}
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
						disabled={saving}
					/>
					{#if !allDay}
						<input
							type="time"
							bind:value={startTime}
							class={inputClass}
							disabled={saving}
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
						disabled={saving}
					/>
					{#if !allDay}
						<input
							type="time"
							bind:value={endTime}
							class={inputClass}
							disabled={saving}
							aria-label="end time"
						/>
					{/if}
				</div>
			</div>
		</div>

		<div class="col-span-full grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
			<div class={fieldClass}>
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
			<div class={fieldClass}>
				<GlobeAlt class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-timezone">timezone</label>
				<input
					id="calendar-event-timezone"
					type="text"
					bind:value={timezone}
					class="{inputClass} col-span-full"
					placeholder="local timezone"
					disabled={saving}
				/>
			</div>
		</div>

		<div class="{fieldClass} col-span-full">
			<Bell class={fieldIconClass} />
			<span class={fieldLabelClass}>notifications</span>
			<div class="col-span-full flex flex-wrap gap-2" aria-label="notification offsets">
				{#each notificationOptions as option (option.value)}
					<button
						type="button"
						class="{pillButtonClass} {notificationOffsets.includes(option.value)
							? activePillClass
							: quietPillClass}"
						disabled={saving}
						onclick={() => toggleNotificationOffset(option.value)}
					>
						{option.label}
					</button>
				{/each}
			</div>
		</div>

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
						disabled={saving}
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
						disabled={saving}
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
						disabled={saving}
						aria-label="location"
					/>
				{:else}
					<input
						type="url"
						bind:value={virtualUrl}
						class={inputClass}
						placeholder="https://"
						disabled={saving}
						aria-label="virtual link"
					/>
				{/if}
			</div>
		</div>

		<div class="{fieldClass} col-span-full">
			<Info class={fieldIconClass} />
			<label class={fieldLabelClass} for="calendar-event-description">description</label>
			<textarea
				id="calendar-event-description"
				bind:value={description}
				class="{inputClass} col-span-full min-h-24 resize-y text-sm"
				placeholder="details, notes, agenda"
				disabled={saving}
			></textarea>
		</div>

		<div class="col-span-full grid grid-cols-2 gap-3 max-[680px]:grid-cols-1">
			<div class={fieldClass}>
				<ClockRotateRight class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-repeat">repeat</label>
				<select
					id="calendar-event-repeat"
					bind:value={recurrence}
					class="{inputClass} col-span-full"
					disabled={saving}
				>
					{#each recurrenceOptions as option (option.value)}
						<option value={option.value}>{option.label}</option>
					{/each}
				</select>
			</div>
			<div class={fieldClass}>
				<Tag class={fieldIconClass} />
				<label class={fieldLabelClass} for="calendar-event-labels">labels</label>
				<input
					id="calendar-event-labels"
					type="text"
					bind:value={labels}
					class="{inputClass} col-span-full"
					placeholder="work, focus"
					disabled={saving}
				/>
			</div>
		</div>

		{#if error}
			<div class="text-destructive col-span-full text-sm">{error}</div>
		{/if}

		<div class="col-span-full flex items-center gap-2 pt-1 max-[680px]:flex-wrap">
			{#if event?.id}
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
			<div class="flex-1 max-[680px]:hidden"></div>
			<button
				type="button"
				class="{actionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent"
				disabled={saving}
				onclick={onClose}
			>
				<XMark class="h-4 w-4" />
				<span>cancel</span>
			</button>
			<button
				type="submit"
				class="{actionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]"
				disabled={saving || !title.trim()}
			>
				<Check class="h-4 w-4" />
				{#if saving}<ShimmerText className="inline-block">saving</ShimmerText>{:else}<span
						>save</span
					>{/if}
			</button>
		</div>
	</form>
</BaseModal>
