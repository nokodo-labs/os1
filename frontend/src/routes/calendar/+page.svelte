<script lang="ts">
	import { browser } from '$app/environment'
	import { goto } from '$app/navigation'
	import { resolve } from '$app/paths'
	import CalendarEventModal from '$lib/components/calendar/CalendarEventModal.svelte'
	import CalendarIcon from '$lib/components/icons/Calendar.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Plus from '$lib/components/icons/Plus.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { useTheme } from '$lib/contexts/themeContext.svelte'
	import {
		calendarEvents,
		calendars,
		scheduledItems,
		type Calendar,
		type CalendarEvent,
		type CalendarEventCreate,
		type CalendarEventUpdate,
		type ScheduledItem,
	} from '$lib/stores/calendars.svelte'
	import type { CalendarType, Event as DayflowEvent } from '@dayflow/core'
	import {
		ViewType,
		createDayView,
		createEvent,
		createEventsPlugin,
		createMonthView,
		createWeekView,
		createYearView,
		temporalToDate,
	} from '@dayflow/core'
	import '@dayflow/core/dist/styles.components.css'
	import { createDragPlugin } from '@dayflow/plugin-drag'
	import { DayFlowCalendar, useCalendarApp } from '@dayflow/svelte'
	import { tick } from 'svelte'
	import { SvelteDate } from 'svelte/reactivity'

	type CalendarFocusDetail = { eventId: string; startAt: string }
	type CalendarFilterDetail = { calendarId: string | null }
	type CalendarFilter = 'all' | typeof REMINDERS_CALENDAR_ID | string
	type ScheduledEventMeta = {
		source: 'event' | 'reminder'
		parentId: string
		containerId: string
		originalOccurrenceAt: string
		readonly: boolean
	}

	const theme = useTheme()
	const chrome = useSystemChrome()
	const DAYFLOW_DEFAULT_CALENDAR_ID = 'personal'
	const REMINDERS_CALENDAR_ID = '__reminders__'
	const REMINDER_EVENT_PREFIX = 'reminder:'

	let currentView = $state<ViewType>(ViewType.WEEK)
	let currentDate: Date = new SvelteDate()
	let eventModalOpen = $state(false)
	let eventModalEventId = $state<string | null>(null)
	let selectedEvent = $state<CalendarEvent | null>(null)
	let eventModalStart = $state<Date | null>(null)
	let selectedCalendarFilter = $state<CalendarFilter>('all')
	let syncingFromStore = false

	const fallbackDayflowCalendars: CalendarType[] = [
		{
			id: DAYFLOW_DEFAULT_CALENDAR_ID,
			name: 'personal',
			colors: {
				lineColor: '#d45446',
				eventColor: '#fee2dc',
				eventSelectedColor: '#f8c8bd',
				textColor: '#7f1d17',
			},
			darkColors: {
				lineColor: '#ff9a88',
				eventColor: '#651f1b',
				eventSelectedColor: '#843027',
				textColor: '#fff1ed',
			},
		},
	]

	const remindersCalendar: CalendarType = {
		id: REMINDERS_CALENDAR_ID,
		name: 'reminders',
		readOnly: true,
		source: 'reminders',
		colors: {
			lineColor: '#22c55e',
			eventColor: '#dcfce7',
			eventSelectedColor: '#bbf7d0',
			textColor: '#14532d',
		},
		darkColors: {
			lineColor: '#86efac',
			eventColor: '#14532d',
			eventSelectedColor: '#166534',
			textColor: '#ecfdf5',
		},
	}

	const viewOptions = [
		{ label: 'day', value: ViewType.DAY },
		{ label: 'week', value: ViewType.WEEK },
		{ label: 'month', value: ViewType.MONTH },
		{ label: 'year', value: ViewType.YEAR },
	]

	const dragPlugin = createDragPlugin({
		enableDrag: true,
		enableResize: true,
		enableCreate: true,
		enableAllDayCreate: true,
	})

	const calendar = useCalendarApp({
		views: [
			createDayView(),
			createWeekView(),
			createMonthView({ showWeekNumbers: true }),
			createYearView({ mode: 'fixed-week' }),
		],
		plugins: [createEventsPlugin(), dragPlugin],
		events: [],
		calendars: fallbackDayflowCalendars,
		defaultCalendar: DAYFLOW_DEFAULT_CALENDAR_ID,
		defaultView: ViewType.WEEK,
		initialDate: currentDate,
		switcherMode: 'buttons',
		theme: { mode: theme.resolvedMode },
		useCalendarHeader: false,
		useEventDetailPanel: false,
		useEventDetailDialog: false,
		callbacks: {
			onViewChange: (view) => {
				currentView = normalizeViewType(view)
			},
			onDateChange: (date) => {
				currentDate = date
			},
			onEventCreate: persistCreatedEvent,
			onEventUpdate: persistUpdatedEvent,
			onEventDelete: persistDeletedEvent,
			onEventClick: openEventFromDayflow,
		},
	})

	function normalizeViewType(view: string): ViewType {
		if (view === ViewType.DAY) return ViewType.DAY
		if (view === ViewType.MONTH) return ViewType.MONTH
		if (view === ViewType.YEAR) return ViewType.YEAR
		return ViewType.WEEK
	}

	function isCalendarFocusDetail(value: unknown): value is CalendarFocusDetail {
		if (typeof value !== 'object' || value === null) return false
		if (!('eventId' in value) || !('startAt' in value)) return false
		return typeof value.eventId === 'string' && typeof value.startAt === 'string'
	}

	function isCalendarFilterDetail(value: unknown): value is CalendarFilterDetail {
		if (typeof value !== 'object' || value === null) return false
		if (!('calendarId' in value)) return false
		return value.calendarId === null || typeof value.calendarId === 'string'
	}

	function shouldRenderScheduledItem(item: ScheduledItem): boolean {
		if (selectedCalendarFilter === 'all') return true
		if (item.kind === 'reminder') return selectedCalendarFilter === REMINDERS_CALENDAR_ID
		return item.calendar_id === selectedCalendarFilter
	}

	const renderedEvents = $derived(
		scheduledItems.all
			.filter(shouldRenderScheduledItem)
			.map(toDayflowEvent)
			.filter(isDayflowEvent)
	)
	const renderedCalendars = $derived(buildRenderedCalendars())
	const rangeTitle = $derived(formatRangeTitle(currentDate, currentView))
	const scheduledWindow = $derived(getScheduledWindow(currentDate, currentView))
	const defaultCalendarId = $derived(calendars.defaultCalendar?.id ?? null)
	const modalDefaultStart = $derived(eventModalStart ?? defaultEventStart())

	$effect(() => {
		calendar.app.setTheme(theme.resolvedMode)
	})

	$effect(() => {
		void calendars.load()
		void scheduledItems.load({
			startAt: scheduledWindow.startAt,
			endAt: scheduledWindow.endAt,
		})
	})

	$effect(() => {
		if (renderedCalendars.length === 0) return
		void syncDayflowCalendars(renderedCalendars)
	})

	$effect(() => {
		syncDayflowEvents(renderedEvents)
	})

	$effect(() => {
		if (!browser) return

		const handleAdd = () => {
			openCreateModal()
		}
		const handleFocus = (event: Event) => {
			if (!(event instanceof CustomEvent)) return
			const detail = event.detail
			if (!isCalendarFocusDetail(detail)) return
			void focusCalendarEvent(detail.eventId, detail.startAt)
		}
		const handleFilter = (event: Event) => {
			if (!(event instanceof CustomEvent)) return
			const detail = event.detail
			if (!isCalendarFilterDetail(detail)) return
			selectedCalendarFilter = detail.calendarId ?? 'all'
			calendar.app.dismissUI()
		}

		window.addEventListener('calendar:add', handleAdd)
		window.addEventListener('calendar:focus', handleFocus)
		window.addEventListener('calendar:filter', handleFilter)
		return () => {
			window.removeEventListener('calendar:add', handleAdd)
			window.removeEventListener('calendar:focus', handleFocus)
			window.removeEventListener('calendar:filter', handleFilter)
		}
	})

	$effect(() => {
		chrome.setContextActions(calendarIslandActions)
		return () => {
			chrome.setContextActions(null)
		}
	})

	function toDayflowEvent(item: ScheduledItem): DayflowEvent | null {
		const start = new SvelteDate(item.effective_start_at)
		if (Number.isNaN(start.getTime())) return null
		const end = item.effective_end_at
			? new SvelteDate(item.effective_end_at)
			: new SvelteDate(start.getTime() + 30 * 60 * 1000)
		return createEvent({
			id: item.id,
			title: item.title,
			description: item.description ?? undefined,
			start,
			end,
			allDay: item.all_day,
			calendarId:
				item.kind === 'reminder'
					? REMINDERS_CALENDAR_ID
					: (item.calendar_id ?? DAYFLOW_DEFAULT_CALENDAR_ID),
			meta: {
				source: item.kind,
				parentId: item.parent_id,
				containerId: item.container_id,
				originalOccurrenceAt: item.original_occurrence_at,
				readonly: item.readonly,
			} satisfies ScheduledEventMeta,
		})
	}

	function isDayflowEvent(event: DayflowEvent | null): event is DayflowEvent {
		return event !== null
	}

	function toDayflowCalendar(calendar: Calendar): CalendarType {
		return {
			id: calendar.id,
			name: calendar.name,
			colors: {
				lineColor: calendar.color,
				eventColor: colorMix(calendar.color, '#ffffff', 0.76),
				eventSelectedColor: colorMix(calendar.color, '#ffffff', 0.58),
				textColor: colorMix(calendar.color, '#111111', 0.4),
			},
			darkColors: {
				lineColor: calendar.color,
				eventColor: colorMix(calendar.color, '#111111', 0.48),
				eventSelectedColor: colorMix(calendar.color, '#111111', 0.34),
				textColor: '#fff7f4',
			},
		}
	}

	function buildRenderedCalendars(): CalendarType[] {
		const sourceCalendars = calendars.all.length
			? calendars.all.map(toDayflowCalendar)
			: fallbackDayflowCalendars
		return [
			...sourceCalendars.map((calendar) => ({
				...calendar,
				isVisible:
					selectedCalendarFilter === 'all' || selectedCalendarFilter === calendar.id,
			})),
			{
				...remindersCalendar,
				isVisible:
					selectedCalendarFilter === 'all' ||
					selectedCalendarFilter === REMINDERS_CALENDAR_ID,
			},
		]
	}

	function colorMix(hex: string, target: string, targetWeight: number): string {
		const source = parseHexColor(hex)
		const destination = parseHexColor(target)
		if (!source || !destination) return hex
		const sourceWeight = 1 - targetWeight
		const red = Math.round(source.red * sourceWeight + destination.red * targetWeight)
		const green = Math.round(source.green * sourceWeight + destination.green * targetWeight)
		const blue = Math.round(source.blue * sourceWeight + destination.blue * targetWeight)
		return `rgb(${red} ${green} ${blue})`
	}

	function parseHexColor(hex: string): { red: number; green: number; blue: number } | null {
		const normalized = hex.trim().replace('#', '')
		if (normalized.length !== 6) return null
		const value = Number.parseInt(normalized, 16)
		if (Number.isNaN(value)) return null
		return {
			red: (value >> 16) & 255,
			green: (value >> 8) & 255,
			blue: value & 255,
		}
	}

	function toCreatePayload(event: DayflowEvent): CalendarEventCreate {
		const startAt = temporalToDate(event.start).toISOString()
		const allDay = Boolean(event.allDay)
		const endAt = normalizeEnd(startAt, temporalToDate(event.end).toISOString(), allDay)
		return {
			title: event.title.trim() || 'new event',
			description: event.description?.trim() || null,
			start_at: startAt,
			end_at: endAt,
			all_day: allDay,
			metadata_: {},
		}
	}

	function toUpdatePayload(event: DayflowEvent): CalendarEventUpdate {
		const startAt = temporalToDate(event.start).toISOString()
		const allDay = Boolean(event.allDay)
		const endAt = normalizeEnd(startAt, temporalToDate(event.end).toISOString(), allDay)
		return {
			title: event.title.trim() || 'new event',
			description: event.description?.trim() || null,
			start_at: startAt,
			end_at: endAt,
			all_day: allDay,
		}
	}

	function normalizeEnd(startAt: string, endAt: string, allDay: boolean): string {
		if (new SvelteDate(endAt).getTime() > new SvelteDate(startAt).getTime()) return endAt
		const fallbackMs = allDay ? 24 * 60 * 60 * 1000 : 60 * 60 * 1000
		return new SvelteDate(new SvelteDate(startAt).getTime() + fallbackMs).toISOString()
	}

	async function persistCreatedEvent(event: DayflowEvent): Promise<void> {
		if (syncingFromStore) return
		if (isReminderDayflowEvent(event)) return
		const calendarId = resolveCalendarId(event.calendarId)
		if (!calendarId) return
		const created = await calendarEvents.create(calendarId, toCreatePayload(event), {
			optimisticId: event.id,
		})
		if (created) await scheduledItems.refresh()
	}

	async function persistUpdatedEvent(event: DayflowEvent): Promise<void> {
		if (syncingFromStore) return
		if (isReminderDayflowEvent(event)) return
		const scheduledItem = scheduledItems.find(event.id)
		if (scheduledItem?.kind === 'event') {
			const updated = await scheduledItems.editEventOccurrence(
				scheduledItem,
				toOccurrenceUpdatePayload(event)
			)
			if (updated) await scheduledItems.refresh()
			return
		}
		const updated = await calendarEvents.update(event.id, toUpdatePayload(event))
		if (updated) await scheduledItems.refresh()
	}

	async function persistDeletedEvent(eventId: string): Promise<void> {
		if (syncingFromStore) return
		if (isReminderEventId(eventId)) return
		const scheduledItem = scheduledItems.find(eventId)
		if (scheduledItem?.kind === 'event') {
			const deleted = await scheduledItems.cancelEventOccurrence(scheduledItem)
			if (deleted) await scheduledItems.refresh()
			return
		}
		const deleted = await calendarEvents.remove(eventId)
		if (deleted) await scheduledItems.refresh()
	}

	function resolveCalendarId(calendarId: string | null | undefined): string | null {
		if (calendarId === REMINDERS_CALENDAR_ID) return null
		if (calendarId && calendarId !== DAYFLOW_DEFAULT_CALENDAR_ID) return calendarId
		return defaultCalendarId ?? calendars.defaultCalendar?.id ?? null
	}

	function openEventFromDayflow(event: DayflowEvent): void {
		calendar.app.dismissUI()
		if (isReminderDayflowEvent(event)) {
			void openReminderSource(event)
			return
		}
		if (browser) window.setTimeout(() => calendar.app.dismissUI(), 0)
		void focusCalendarEvent(event.id, temporalToDate(event.start).toISOString())
	}

	function isReminderEventId(eventId: string): boolean {
		return eventId.startsWith(REMINDER_EVENT_PREFIX)
	}

	function isReminderDayflowEvent(event: DayflowEvent): boolean {
		return event.calendarId === REMINDERS_CALENDAR_ID || isReminderEventId(event.id)
	}

	function getScheduledMeta(event: DayflowEvent): ScheduledEventMeta | null {
		const meta = event.meta
		if (!meta || (meta.source !== 'event' && meta.source !== 'reminder')) return null
		if (typeof meta.parentId !== 'string') return null
		if (typeof meta.containerId !== 'string') return null
		if (typeof meta.originalOccurrenceAt !== 'string') return null
		if (typeof meta.readonly !== 'boolean') return null
		return {
			source: meta.source,
			parentId: meta.parentId,
			containerId: meta.containerId,
			originalOccurrenceAt: meta.originalOccurrenceAt,
			readonly: meta.readonly,
		}
	}

	async function openReminderSource(event: DayflowEvent): Promise<void> {
		const meta = getScheduledMeta(event)
		const target = meta?.containerId
			? resolve('/reminders/lists/[listId]', { listId: meta.containerId })
			: resolve('/reminders')
		await goto(target, { keepFocus: true, noScroll: true })
	}

	function eventSignature(event: DayflowEvent): string {
		return JSON.stringify({
			title: event.title,
			description: event.description ?? null,
			start: temporalToDate(event.start).toISOString(),
			end: temporalToDate(event.end).toISOString(),
			allDay: Boolean(event.allDay),
			calendarId: event.calendarId ?? DAYFLOW_DEFAULT_CALENDAR_ID,
			source: event.meta?.source ?? null,
		})
	}

	function toOccurrenceUpdatePayload(
		event: DayflowEvent
	): Omit<
		NonNullable<Parameters<typeof scheduledItems.editEventOccurrence>[1]>,
		'original_occurrence_at'
	> {
		const startAt = temporalToDate(event.start).toISOString()
		const allDay = Boolean(event.allDay)
		const endAt = normalizeEnd(startAt, temporalToDate(event.end).toISOString(), allDay)
		return {
			new_start_at: startAt,
			new_end_at: endAt,
			title: event.title.trim() || 'new event',
			description: event.description?.trim() || null,
		}
	}

	function getScheduledWindow(date: Date, view: ViewType): { startAt: string; endAt: string } {
		const start = new SvelteDate(date)
		const end = new SvelteDate(date)
		if (view === ViewType.DAY) {
			start.setHours(0, 0, 0, 0)
			end.setHours(23, 59, 59, 999)
		} else if (view === ViewType.WEEK) {
			start.setDate(start.getDate() - start.getDay())
			start.setHours(0, 0, 0, 0)
			end.setTime(start.getTime() + 7 * 24 * 60 * 60 * 1000 - 1)
		} else if (view === ViewType.MONTH) {
			start.setDate(1)
			start.setHours(0, 0, 0, 0)
			end.setFullYear(start.getFullYear(), start.getMonth() + 1, 0)
			end.setHours(23, 59, 59, 999)
		} else {
			start.setMonth(0, 1)
			start.setHours(0, 0, 0, 0)
			end.setFullYear(start.getFullYear(), 11, 31)
			end.setHours(23, 59, 59, 999)
		}
		return { startAt: start.toISOString(), endAt: end.toISOString() }
	}

	function syncDayflowEvents(nextEvents: DayflowEvent[]): void {
		const currentEvents = calendar.app.getEvents()
		const currentById = new Map(currentEvents.map((event) => [event.id, event]))
		const nextById = new Map(nextEvents.map((event) => [event.id, event]))
		const add = nextEvents.filter((event) => !currentById.has(event.id))
		const update = nextEvents
			.filter((event) => {
				const current = currentById.get(event.id)
				return current && eventSignature(current) !== eventSignature(event)
			})
			.map((event) => ({ id: event.id, updates: event }))
		const remove = currentEvents
			.filter((event) => !nextById.has(event.id))
			.map((event) => event.id)

		if (add.length === 0 && update.length === 0 && remove.length === 0) return

		syncingFromStore = true
		try {
			calendar.applyEventsChanges({ add, update, delete: remove }, true)
		} finally {
			syncingFromStore = false
		}
	}

	async function syncDayflowCalendars(nextCalendars: CalendarType[]): Promise<void> {
		const currentCalendars = new Map(calendar.getCalendars().map((item) => [item.id, item]))
		const nextIds = new Set(nextCalendars.map((item) => item.id))
		for (const currentCalendar of currentCalendars.values()) {
			if (!nextIds.has(currentCalendar.id)) {
				await calendar.app.deleteCalendar(currentCalendar.id)
			}
		}
		for (const nextCalendar of nextCalendars) {
			if (currentCalendars.has(nextCalendar.id)) {
				calendar.app.updateCalendar(nextCalendar.id, nextCalendar)
			} else {
				await calendar.createCalendar(nextCalendar)
			}
		}
	}

	function roundToNextHour(date: Date): Date {
		const rounded = new SvelteDate(date)
		if (rounded.getMinutes() > 0 || rounded.getSeconds() > 0 || rounded.getMilliseconds() > 0) {
			rounded.setHours(rounded.getHours() + 1)
		}
		rounded.setMinutes(0, 0, 0)
		return rounded
	}

	function defaultEventStart(): Date {
		const selected = new SvelteDate(currentDate)
		const today = new SvelteDate()
		const sameDay = selected.toDateString() === today.toDateString()
		if (sameDay) return roundToNextHour(today)
		selected.setHours(9, 0, 0, 0)
		return selected
	}

	function openCreateModal(start?: Date): void {
		eventModalEventId = null
		selectedEvent = null
		eventModalStart = start ?? defaultEventStart()
		eventModalOpen = true
	}

	function closeEventModal(): void {
		eventModalOpen = false
		eventModalEventId = null
		selectedEvent = null
		eventModalStart = null
	}

	async function handleSavedEvent(event: CalendarEvent): Promise<void> {
		selectedEvent = event
		await scheduledItems.refresh()
		currentDate = new SvelteDate(event.start_at)
		calendar.setCurrentDate(currentDate)
	}

	async function handleDeletedEvent(eventId: string): Promise<void> {
		await scheduledItems.refresh()
		calendar.highlightEvent(null)
		calendar.app.selectEvent(null)
		if (eventModalEventId === eventId) eventModalEventId = null
		selectedEvent = null
	}

	async function focusCalendarEvent(eventId: string, startAt: string): Promise<void> {
		if (isReminderEventId(eventId)) {
			await selectCalendarEvent(eventId, startAt)
			const event = calendar.app.getEvents().find((item) => item.id === eventId)
			if (event) await openReminderSource(event)
			return
		}
		const scheduledItem = scheduledItems.find(eventId)
		if (scheduledItem?.kind === 'event') {
			await selectCalendarEvent(eventId, startAt)
			const calendarId = scheduledItem.calendar_id ?? scheduledItem.container_id
			const source = await calendarEvents.get(scheduledItem.parent_id, calendarId)
			if (!source) return
			selectedEvent = source
			eventModalEventId = source.id
			eventModalStart = new SvelteDate(startAt)
			eventModalOpen = true
			return
		}
		await selectCalendarEvent(eventId, startAt)
		selectedEvent = calendarEvents.all.find((event) => event.id === eventId) ?? null
		eventModalEventId = eventId
		eventModalStart = new SvelteDate(startAt)
		eventModalOpen = true
	}

	async function selectCalendarEvent(eventId: string, startAt: string): Promise<void> {
		const start = new SvelteDate(startAt)
		currentDate = start
		calendar.setCurrentDate(start)
		await tick()
		calendar.highlightEvent(eventId)
		calendar.app.selectEvent(eventId)
	}

	function goToPrevious(): void {
		calendar.goToPrevious()
		currentDate = calendar.app.getCurrentDate()
	}

	function goToToday(): void {
		calendar.goToToday()
		currentDate = calendar.app.getCurrentDate()
	}

	function goToNext(): void {
		calendar.goToNext()
		currentDate = calendar.app.getCurrentDate()
	}

	function changeView(view: ViewType): void {
		currentView = view
		calendar.changeView(view)
	}

	function formatRangeTitle(date: Date, view: ViewType): string {
		if (view === ViewType.YEAR) return String(date.getFullYear())
		if (view === ViewType.MONTH) {
			return new Intl.DateTimeFormat(undefined, { month: 'long', year: 'numeric' })
				.format(date)
				.toLowerCase()
		}
		if (view === ViewType.DAY) {
			return new Intl.DateTimeFormat(undefined, {
				weekday: 'long',
				month: 'long',
				day: 'numeric',
			})
				.format(date)
				.toLowerCase()
		}

		const start = new SvelteDate(date)
		start.setDate(date.getDate() - date.getDay())
		const end = new SvelteDate(start)
		end.setDate(start.getDate() + 6)
		const formatter = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' })
		return `${formatter.format(start).toLowerCase()} - ${formatter.format(end).toLowerCase()}`
	}
</script>

{#snippet calendarIslandActions()}
	<button
		type="button"
		class="rounded-pill flex h-8 w-8 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		aria-label="previous date"
		onclick={goToPrevious}
	>
		<ChevronLeft />
	</button>
	<button
		type="button"
		class="rounded-pill flex h-8 w-8 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		aria-label="today"
		onclick={goToToday}
	>
		<CalendarIcon class="h-4 w-4" />
	</button>
	<button
		type="button"
		class="rounded-pill flex h-8 w-8 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		aria-label="next date"
		onclick={goToNext}
	>
		<ChevronRight />
	</button>
	<button
		type="button"
		class="rounded-pill flex h-8 w-8 cursor-pointer items-center justify-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		aria-label="create event"
		onclick={() => openCreateModal()}
	>
		<Plus class="h-4 w-4" />
	</button>
{/snippet}

<div
	class="calendar-page flex h-full min-h-0 flex-1 flex-col gap-[clamp(10px,1.1vw,14px)] overflow-hidden"
>
	<header
		class="liquid-glass liquid-glass--frosted border-foreground/14 flex min-h-17 shrink-0 items-center gap-4 rounded-[18px] border px-4 py-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] max-[888px]:flex-col max-[888px]:items-stretch max-[888px]:gap-3 max-[888px]:p-3"
	>
		<div class="min-w-0 flex-1">
			<div class="text-foreground/45 text-xs font-medium tracking-[0.12em] uppercase">
				{currentView.toLowerCase()}
			</div>
			<h2 class="text-foreground min-w-0 truncate text-xl font-semibold">{rangeTitle}</h2>
		</div>

		<div class="flex min-w-0 items-center gap-2 max-[888px]:flex-wrap">
			<div
				class="border-foreground/10 bg-foreground/6 flex max-w-full items-center overflow-x-auto rounded-full border p-0.5"
				role="tablist"
				aria-label="calendar view"
			>
				{#each viewOptions as option (option.value)}
					<button
						type="button"
						role="tab"
						aria-selected={currentView === option.value}
						class="rounded-pill flex min-h-8 cursor-pointer items-center border-none bg-transparent px-3 text-[0.78rem] font-semibold transition-all duration-150 active:scale-[0.97] {currentView ===
						option.value
							? 'bg-foreground/10 text-foreground'
							: 'text-foreground/75 hover:bg-foreground/6 hover:text-foreground'}"
						onclick={() => changeView(option.value)}
					>
						{option.label}
					</button>
				{/each}
			</div>
		</div>
	</header>

	<div
		class="nokodo-calendar liquid-glass liquid-glass--frosted border-foreground/16 isolate min-h-0 flex-1 overflow-hidden rounded-(--calendar-radius) border shadow-[0_22px_64px_rgb(0_0_0/0.28),inset_0_1px_0_rgb(255_255_255/0.14)] [--calendar-radius:clamp(16px,1.8vw,24px)] [clip-path:inset(0_round_var(--calendar-radius))] max-[888px]:[--calendar-radius:18px]"
	>
		<DayFlowCalendar {calendar} />
	</div>

	<CalendarEventModal
		open={eventModalOpen}
		defaultStart={modalDefaultStart}
		{defaultCalendarId}
		event={selectedEvent}
		onClose={closeEventModal}
		onSaved={handleSavedEvent}
		onDeleted={handleDeletedEvent}
	/>
</div>

<style>
	.nokodo-calendar :global(.df-calendar-container),
	:global(.df-portal) {
		--df-color-background: rgb(250 248 246 / 0.64);
		--df-color-foreground: rgb(28 24 22);
		--df-color-card: rgb(255 255 255 / 0.74);
		--df-color-card-foreground: rgb(28 24 22);
		--df-color-muted: rgb(28 24 22 / 0.07);
		--df-color-muted-foreground: rgb(28 24 22 / 0.56);
		--df-color-border: rgb(28 24 22 / 0.13);
		--df-color-hover: rgb(212 84 70 / 0.1);
		--df-color-primary: rgb(212 84 70);
		--df-color-primary-foreground: rgb(255 250 248);
		--df-color-secondary: rgb(255 255 255 / 0.68);
		--df-color-secondary-foreground: rgb(28 24 22);
		--df-calendar-height: 100%;
		height: 100%;
		min-height: 0;
		overflow: hidden;
		background: color-mix(in oklch, var(--background) 58%, transparent);
		border: 0;
		border-radius: inherit;
		box-shadow: none;
		font-family: inherit;
		text-transform: lowercase;
		backdrop-filter: blur(26px) saturate(1.18);
	}

	:global(.dark) .nokodo-calendar :global(.df-calendar-container),
	:global(.dark) :global(.df-portal) {
		--df-color-background: rgb(14 12 12 / 0.56);
		--df-color-foreground: rgb(250 246 244);
		--df-color-card: rgb(27 24 24 / 0.72);
		--df-color-card-foreground: rgb(250 246 244);
		--df-color-muted: rgb(255 255 255 / 0.08);
		--df-color-muted-foreground: rgb(255 246 242 / 0.6);
		--df-color-border: rgb(255 246 242 / 0.14);
		--df-color-hover: rgb(255 154 136 / 0.13);
		--df-color-primary: rgb(255 154 136);
		--df-color-primary-foreground: rgb(45 16 13);
		--df-color-secondary: rgb(255 255 255 / 0.11);
		--df-color-secondary-foreground: rgb(250 246 244);
		background: rgb(14 12 12 / 0.46);
	}

	.nokodo-calendar :global(.df-calendar-shell),
	.nokodo-calendar :global(.df-calendar-container),
	.nokodo-calendar :global(.df-calendar-root),
	.nokodo-calendar :global(.df-calendar-content-wrap),
	.nokodo-calendar :global(.df-calendar-renderer),
	.nokodo-calendar :global(.df-calendar-view-container),
	.nokodo-calendar :global(.df-header),
	.nokodo-calendar :global(.df-week-header-row),
	.nokodo-calendar :global(.df-week-header),
	.nokodo-calendar :global(.df-month-view),
	.nokodo-calendar :global(.df-calendar),
	.nokodo-calendar :global(.df-day-view),
	.nokodo-calendar :global(.df-year-fixed),
	.nokodo-calendar :global(.df-year-grid) {
		min-height: 0;
		background-color: transparent;
		border-radius: inherit;
		overflow: hidden;
	}

	.nokodo-calendar :global(.df-header),
	.nokodo-calendar :global(.df-view-header-container),
	.nokodo-calendar :global(.df-view-switcher),
	.nokodo-calendar :global(.df-navigation),
	.nokodo-calendar :global(.df-right-panel-calendar-header),
	.nokodo-calendar :global(#dayflow-add-event-btn),
	.nokodo-calendar :global(.df-search-group),
	.nokodo-calendar :global(.df-toolbar),
	.nokodo-calendar :global(.df-calendar-header) {
		display: none;
	}

	.nokodo-calendar :global(.df-event),
	.nokodo-calendar :global(.df-month-segment-event) {
		border-radius: 10px;
		box-shadow: 0 8px 18px rgb(0 0 0 / 0.14);
	}

	.nokodo-calendar :global(.df-event-detail-panel),
	:global(.df-dialog-container),
	:global(.df-event-dialog-overlay),
	:global(.df-mobile-event-drawer) {
		display: none !important;
	}
</style>
