/** calendar store - caches calendars and events with API persistence. */

import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getAccessToken, onAccessTokenChanged } from '$lib/auth/session.svelte'
import { showError } from '$lib/stores/notifications.svelte'
import { SvelteDate, SvelteMap } from 'svelte/reactivity'

export type Calendar = components['schemas']['Calendar']
export type CalendarCreate = components['schemas']['CalendarCreate']
export type CalendarUpdate = components['schemas']['CalendarUpdate']
export type CalendarEvent = components['schemas']['CalendarEvent']
export type CalendarEventCreate = components['schemas']['CalendarEventCreate']
export type CalendarEventUpdate = components['schemas']['CalendarEventUpdate']
export type ScheduledItem = components['schemas']['ScheduledItem']
export type CalendarOccurrenceEdit = components['schemas']['CalendarOccurrenceEdit']
export type CalendarOccurrenceCancel = components['schemas']['CalendarOccurrenceCancel']

type ScheduledItemsWindow = {
	startAt: string
	endAt: string
	includeCompleted: boolean
}

const CACHE_TTL_MS = 10 * 60 * 1000

function isFresh(fetchedAt: number | null): boolean {
	return fetchedAt !== null && Date.now() - fetchedAt < CACHE_TTL_MS
}

function createTempId(): string {
	return `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function sortCalendars(items: Calendar[]): Calendar[] {
	return items.toSorted((a, b) => {
		const positionDelta = a.position - b.position
		if (positionDelta !== 0) return positionDelta
		return a.name.localeCompare(b.name)
	})
}

function sortEvents(events: CalendarEvent[]): CalendarEvent[] {
	return events.toSorted(
		(a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime()
	)
}

function sortScheduledItems(items: ScheduledItem[]): ScheduledItem[] {
	return items.toSorted(
		(a, b) =>
			new Date(a.effective_start_at).getTime() - new Date(b.effective_start_at).getTime()
	)
}

class CalendarsStore {
	readonly #calendarsMap = new SvelteMap<string, Calendar>()
	#fetchedAt = $state<number | null>(null)
	#isLoading = $state(true)
	#inFlight: Promise<Calendar[]> | null = null
	#unsubscribe: (() => void) | null = null

	get hydrated() {
		return this.#fetchedAt !== null
	}

	get loading() {
		return this.#isLoading
	}

	get all(): Calendar[] {
		return sortCalendars([...this.#calendarsMap.values()])
	}

	get defaultCalendar(): Calendar | null {
		return this.all.find((calendar) => calendar.is_default) ?? this.all[0] ?? null
	}

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	async load(options?: { force?: boolean }): Promise<Calendar[]> {
		const force = options?.force ?? false
		if (!force && isFresh(this.#fetchedAt)) {
			this.#isLoading = false
			return this.all
		}
		if (this.#inFlight) return this.#inFlight

		this.#isLoading = true
		this.#inFlight = (async () => {
			const { data, error } = await api.GET('/v1/calendars', {
				params: {
					query: {
						limit: 500,
						sort_by: 'position',
						sort_dir: 'asc',
					},
				},
			})
			if (error || !data) return this.all

			this.#calendarsMap.clear()
			for (const calendar of data) this.#upsert(calendar)
			this.#fetchedAt = Date.now()
			return this.all
		})()

		try {
			return await this.#inFlight
		} finally {
			this.#inFlight = null
			this.#isLoading = false
		}
	}

	async create(data: CalendarCreate): Promise<Calendar | null> {
		try {
			const { data: created, error } = await api.POST('/v1/calendars', {
				body: data,
			})
			if (error || !created) {
				showError('could not create calendar')
				return null
			}
			this.#upsert(created)
			return created
		} catch {
			showError('could not create calendar')
			return null
		}
	}

	async update(calendarId: string, updates: CalendarUpdate): Promise<Calendar | null> {
		const existing = this.#calendarsMap.get(calendarId)
		try {
			const { data, error } = await api.PATCH('/v1/calendars/{calendar_id}', {
				params: { path: { calendar_id: calendarId } },
				body: updates,
			})
			if (error || !data) {
				if (existing) this.#calendarsMap.set(calendarId, existing)
				showError('could not save calendar')
				return null
			}
			this.#upsert(data)
			return data
		} catch {
			if (existing) this.#calendarsMap.set(calendarId, existing)
			showError('could not save calendar')
			return null
		}
	}

	async remove(calendarId: string): Promise<boolean> {
		const existing = this.#calendarsMap.get(calendarId)
		if (!existing) return false
		this.#calendarsMap.delete(calendarId)
		try {
			const { error } = await api.DELETE('/v1/calendars/{calendar_id}', {
				params: { path: { calendar_id: calendarId } },
			})
			if (error) {
				this.#calendarsMap.set(calendarId, existing)
				showError('could not delete calendar')
				return false
			}
			calendarEvents.removeCalendarEvents(calendarId)
			return true
		} catch {
			this.#calendarsMap.set(calendarId, existing)
			showError('could not delete calendar')
			return false
		}
	}

	invalidate(): void {
		this.#fetchedAt = null
	}

	clear(): void {
		this.#calendarsMap.clear()
		this.#fetchedAt = null
	}

	#upsert(calendar: Calendar): void {
		this.#calendarsMap.set(calendar.id, calendar)
	}

	#remove(calendarId: string): void {
		this.#calendarsMap.delete(calendarId)
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		const data = message.data as Record<string, unknown> | undefined
		if (!data) return

		if (message.type === 'calendar.created' || message.type === 'calendar.updated') {
			const calendar = data as unknown as Calendar
			if (calendar?.id) this.#upsert(calendar)
		} else if (message.type === 'calendar.deleted') {
			const calendar = data as unknown as Calendar
			if (calendar?.id) this.#remove(calendar.id)
		}
	}
}

class CalendarEventsStore {
	readonly #eventsMap = new SvelteMap<string, CalendarEvent>()
	#fetchedAt = $state<number | null>(null)
	#isLoading = $state(true)
	#inFlight: Promise<CalendarEvent[]> | null = null
	#unsubscribe: (() => void) | null = null

	get hydrated() {
		return this.#fetchedAt !== null
	}

	get loading() {
		return this.#isLoading
	}

	get all(): CalendarEvent[] {
		return sortEvents([...this.#eventsMap.values()])
	}

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	async load(options?: {
		force?: boolean
		startAt?: string
		endAt?: string
		calendarId?: string
		q?: string
	}): Promise<CalendarEvent[]> {
		const force = options?.force ?? false
		if (!force && isFresh(this.#fetchedAt)) {
			this.#isLoading = false
			return this.all
		}
		if (this.#inFlight) return this.#inFlight

		this.#isLoading = true
		this.#inFlight = (async () => {
			const query: {
				start_at?: string
				end_at?: string
				q?: string
				limit: number
				sort_by: 'start_at'
				sort_dir: 'asc'
			} = {
				limit: 1000,
				sort_by: 'start_at',
				sort_dir: 'asc',
			}
			if (options?.startAt) query.start_at = options.startAt
			if (options?.endAt) query.end_at = options.endAt
			if (options?.q) query.q = options.q

			const calendarIds = options?.calendarId
				? [options.calendarId]
				: (calendars.hydrated ? calendars.all : await calendars.load()).map(
						(calendar) => calendar.id
					)

			const responses = await Promise.all(
				calendarIds.map((calendarId) =>
					api.GET('/v1/calendars/{calendar_id}/events', {
						params: { path: { calendar_id: calendarId }, query },
					})
				)
			)
			const fetched: CalendarEvent[] = []
			for (const response of responses) {
				if (response.error || !response.data) continue
				fetched.push(...response.data)
			}

			if (options?.calendarId) {
				this.#removeCalendarEvents(options.calendarId)
			} else {
				this.#eventsMap.clear()
			}
			for (const event of fetched) this.#upsert(event)
			this.#fetchedAt = Date.now()
			return this.all
		})()

		try {
			return await this.#inFlight
		} finally {
			this.#inFlight = null
			this.#isLoading = false
		}
	}

	async get(eventId: string, calendarId: string): Promise<CalendarEvent | null> {
		const cached = this.#eventsMap.get(eventId)
		if (cached) return cached
		try {
			const { data, error } = await api.GET('/v1/calendars/{calendar_id}/events/{event_id}', {
				params: { path: { calendar_id: calendarId, event_id: eventId } },
			})
			if (error || !data) return null
			this.#upsert(data)
			return data
		} catch {
			return null
		}
	}

	async create(
		calendarId: string,
		data: CalendarEventCreate,
		options?: { optimisticId?: string; rollback?: boolean }
	): Promise<CalendarEvent | null> {
		const id = options?.optimisticId ?? createTempId()
		const doRollback = options?.rollback ?? true
		const placeholder = this.#toPlaceholder(calendarId, data, id)
		this.#eventsMap.set(id, placeholder)

		try {
			const { data: created, error } = await api.POST('/v1/calendars/{calendar_id}/events', {
				params: { path: { calendar_id: calendarId } },
				body: data,
			})

			if (error || !created) {
				if (doRollback) this.#eventsMap.delete(id)
				showError('could not create event')
				return null
			}

			this.#eventsMap.delete(id)
			this.#upsert(created)
			return created
		} catch {
			if (doRollback) this.#eventsMap.delete(id)
			showError('could not create event')
			return null
		}
	}

	async update(
		eventId: string,
		updates: CalendarEventUpdate,
		options?: { rollback?: boolean }
	): Promise<CalendarEvent | null> {
		const existing = this.#eventsMap.get(eventId)
		if (!existing) return null
		const doRollback = options?.rollback ?? true
		const optimistic: CalendarEvent = {
			...existing,
			metadata_: updates.metadata_ ?? existing.metadata_ ?? {},
			title: updates.title ?? existing.title,
			description: 'description' in updates ? updates.description : existing.description,
			start_at: updates.start_at ?? existing.start_at,
			end_at: updates.end_at ?? existing.end_at,
			all_day: updates.all_day ?? existing.all_day,
			calendar_id: existing.calendar_id,
			timezone: 'timezone' in updates ? updates.timezone : existing.timezone,
			recurrence: 'recurrence' in updates ? updates.recurrence : existing.recurrence,
			notification_offsets:
				'notification_offsets' in updates
					? (updates.notification_offsets ?? [])
					: (existing.notification_offsets ?? []),
			location: 'location' in updates ? updates.location : existing.location,
			virtual_url: 'virtual_url' in updates ? updates.virtual_url : existing.virtual_url,
			labels: updates.labels ?? existing.labels ?? [],
			updated_at: new SvelteDate().toISOString(),
		}
		this.#eventsMap.set(eventId, optimistic)

		if (eventId.startsWith('temp-')) return optimistic

		try {
			const { data, error } = await api.PATCH(
				'/v1/calendars/{calendar_id}/events/{event_id}',
				{
					params: {
						path: { calendar_id: existing.calendar_id, event_id: eventId },
					},
					body: updates,
				}
			)

			if (error || !data) {
				if (doRollback) this.#eventsMap.set(eventId, existing)
				showError('could not save event')
				return null
			}

			this.#upsert(data)
			return data
		} catch {
			if (doRollback) this.#eventsMap.set(eventId, existing)
			showError('could not save event')
			return null
		}
	}

	async remove(eventId: string, options?: { rollback?: boolean }): Promise<boolean> {
		const existing = this.#eventsMap.get(eventId)
		if (!existing) return false
		const doRollback = options?.rollback ?? true
		this.#eventsMap.delete(eventId)

		if (eventId.startsWith('temp-')) return true

		try {
			const { error } = await api.DELETE('/v1/calendars/{calendar_id}/events/{event_id}', {
				params: { path: { calendar_id: existing.calendar_id, event_id: eventId } },
			})
			if (error) {
				if (doRollback) this.#eventsMap.set(eventId, existing)
				showError('could not delete event')
				return false
			}
			return true
		} catch {
			if (doRollback) this.#eventsMap.set(eventId, existing)
			showError('could not delete event')
			return false
		}
	}

	invalidate(): void {
		this.#fetchedAt = null
	}

	clear(): void {
		this.#eventsMap.clear()
		this.#fetchedAt = null
	}

	removeCalendarEvents(calendarId: string): void {
		this.#removeCalendarEvents(calendarId)
	}

	#upsert(event: CalendarEvent): void {
		this.#eventsMap.set(event.id, event)
	}

	#removeCalendarEvents(calendarId: string): void {
		for (const event of this.#eventsMap.values()) {
			if (event.calendar_id === calendarId) this.#eventsMap.delete(event.id)
		}
	}

	#toPlaceholder(calendarId: string, data: CalendarEventCreate, id: string): CalendarEvent {
		const now = new SvelteDate().toISOString()
		return {
			...data,
			metadata_: data.metadata_ ?? {},
			all_day: data.all_day ?? false,
			calendar_id: calendarId,
			notification_offsets: data.notification_offsets ?? [],
			labels: data.labels ?? [],
			id,
			owner_id: '',
			created_at: now,
			updated_at: now,
		}
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		const data = message.data as Record<string, unknown> | undefined
		if (!data) return

		if (
			message.type === 'calendar.event.created' ||
			message.type === 'calendar.event.updated'
		) {
			const event = data as unknown as CalendarEvent
			if (event?.id) this.#upsert(event)
		} else if (message.type === 'calendar.event.deleted') {
			const event = data as unknown as CalendarEvent
			if (event?.id) this.#eventsMap.delete(event.id)
		}
	}
}

class ScheduledItemsStore {
	readonly #itemsMap = new SvelteMap<string, ScheduledItem>()
	readonly #windowFetchedAt = new SvelteMap<string, number>()
	readonly #windows = new SvelteMap<string, ScheduledItemsWindow>()
	#isLoading = $state(true)
	#inFlight = new Map<string, Promise<ScheduledItem[]>>()
	#lastWindow: ScheduledItemsWindow | null = null
	#unsubscribe: (() => void) | null = null

	get hydrated() {
		return this.#windowFetchedAt.size > 0
	}

	get loading() {
		return this.#isLoading
	}

	get all(): ScheduledItem[] {
		return sortScheduledItems([...this.#itemsMap.values()])
	}

	init(): void {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
	}

	cleanup(): void {
		this.#unsubscribe?.()
		this.#unsubscribe = null
	}

	async load(options: {
		force?: boolean
		startAt: string
		endAt: string
		includeCompleted?: boolean
	}): Promise<ScheduledItem[]> {
		const includeCompleted = options.includeCompleted ?? false
		const window = {
			startAt: options.startAt,
			endAt: options.endAt,
			includeCompleted,
		}
		const windowKey = this.#windowKey(window)
		const fetchedAt = this.#windowFetchedAt.get(windowKey) ?? null
		const force = options.force ?? false
		if (!force && isFresh(fetchedAt)) {
			this.#isLoading = false
			return this.all
		}
		const existingInFlight = this.#inFlight.get(windowKey)
		if (existingInFlight) return existingInFlight

		this.#isLoading = true
		const inFlight = (async () => {
			const { data, error } = await api.GET('/v1/scheduled-items', {
				params: {
					query: {
						start_at: window.startAt,
						end_at: window.endAt,
						include_completed: includeCompleted,
						limit: 3000,
					},
				},
			})
			if (error || !data) return this.all

			this.#replaceWindowItems(window, data)
			this.#windows.set(windowKey, window)
			this.#windowFetchedAt.set(windowKey, Date.now())
			this.#lastWindow = window
			return this.all
		})()
		this.#inFlight.set(windowKey, inFlight)

		try {
			return await inFlight
		} finally {
			this.#inFlight.delete(windowKey)
			this.#isLoading = this.#inFlight.size > 0
		}
	}

	async refresh(): Promise<ScheduledItem[]> {
		const windows = [...this.#windows.values()]
		if (windows.length === 0 && this.#lastWindow) windows.push(this.#lastWindow)
		if (windows.length === 0) return this.all
		let result = this.all
		for (const window of windows) {
			result = await this.load({
				force: true,
				startAt: window.startAt,
				endAt: window.endAt,
				includeCompleted: window.includeCompleted,
			})
		}
		return result
	}

	find(itemId: string): ScheduledItem | null {
		return this.#itemsMap.get(itemId) ?? null
	}

	async editEventOccurrence(
		item: ScheduledItem,
		updates: Omit<CalendarOccurrenceEdit, 'original_occurrence_at'>
	): Promise<ScheduledItem | null> {
		if (item.kind !== 'event' || !item.calendar_id) return null
		try {
			const { data, error } = await api.PATCH(
				'/v1/calendars/{calendar_id}/events/{event_id}/occurrence',
				{
					params: {
						path: {
							calendar_id: item.calendar_id,
							event_id: item.parent_id,
						},
					},
					body: {
						...updates,
						original_occurrence_at: item.original_occurrence_at,
					},
				}
			)
			if (error || !data) {
				showError('could not save event')
				return null
			}
			this.#itemsMap.set(data.id, data)
			return data
		} catch {
			showError('could not save event')
			return null
		}
	}

	async cancelEventOccurrence(item: ScheduledItem): Promise<boolean> {
		if (item.kind !== 'event' || !item.calendar_id) return false
		const body: CalendarOccurrenceCancel = {
			original_occurrence_at: item.original_occurrence_at,
		}
		this.#itemsMap.delete(item.id)
		try {
			const { error } = await api.POST(
				'/v1/calendars/{calendar_id}/events/{event_id}/occurrence/cancel',
				{
					params: {
						path: {
							calendar_id: item.calendar_id,
							event_id: item.parent_id,
						},
					},
					body,
				}
			)
			if (error) {
				this.#itemsMap.set(item.id, item)
				showError('could not delete event')
				return false
			}
			return true
		} catch {
			this.#itemsMap.set(item.id, item)
			showError('could not delete event')
			return false
		}
	}

	invalidate(): void {
		this.#windowFetchedAt.clear()
	}

	clear(): void {
		this.#itemsMap.clear()
		this.#windowFetchedAt.clear()
		this.#windows.clear()
		this.#lastWindow = null
	}

	#windowKey(window: ScheduledItemsWindow): string {
		return `${window.startAt}:${window.endAt}:${window.includeCompleted ? '1' : '0'}`
	}

	#replaceWindowItems(window: ScheduledItemsWindow, items: ScheduledItem[]): void {
		const startAt = Date.parse(window.startAt)
		const endAt = Date.parse(window.endAt)
		if (Number.isNaN(startAt) || Number.isNaN(endAt)) return
		for (const item of this.#itemsMap.values()) {
			const itemStart = Date.parse(item.effective_start_at)
			if (!Number.isNaN(itemStart) && itemStart >= startAt && itemStart <= endAt) {
				this.#itemsMap.delete(item.id)
			}
		}
		for (const item of items) this.#itemsMap.set(item.id, item)
	}

	#handleStreamEvent = (message: StreamMessage): void => {
		if (message.type.startsWith('calendar') || message.type.startsWith('reminder')) {
			this.invalidate()
		}
	}
}

export const calendars = new CalendarsStore()
export const calendarEvents = new CalendarEventsStore()
export const scheduledItems = new ScheduledItemsStore()

if (browser) {
	onAccessTokenChanged((token) => {
		if (token) {
			calendars.init()
			calendarEvents.init()
			scheduledItems.init()
		} else {
			calendars.cleanup()
			calendarEvents.cleanup()
			scheduledItems.cleanup()
			calendars.clear()
			calendarEvents.clear()
			scheduledItems.clear()
		}
	})

	if (getAccessToken()) {
		calendars.init()
		calendarEvents.init()
		scheduledItems.init()
	}
}
