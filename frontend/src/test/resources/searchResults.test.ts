import type { SearchResult } from '$lib/api/streaming'
import { searchResultToResource } from '$lib/resources/searchResults'
import { describe, expect, it } from 'vitest'

/** Build a minimal generated search result fixture. */
function makeSearchResult(overrides: Partial<SearchResult>): SearchResult {
	return {
		type: 'reminder_list',
		id: 'reminder_list_1',
		title: 'send draft',
		preview: null,
		created_at: '2025-01-01T00:00:00.000Z',
		updated_at: '2025-01-02T00:00:00.000Z',
		...overrides,
	}
}

describe('searchResultToResource', () => {
	it('routes to the container and carries the anchor for a matched reminder', () => {
		const resource = searchResultToResource(
			makeSearchResult({
				anchor: { type: 'reminder', id: 'reminder_1' },
			})
		)

		expect(resource.type).toBe('reminder_list')
		expect(resource.anchor).toEqual({ type: 'reminder', id: 'reminder_1' })
		expect(resource.href).toBe('/reminders/lists/reminder_list_1?reminder=reminder_1')
	})

	it('routes to the container alone when the list itself matched', () => {
		const resource = searchResultToResource(makeSearchResult({ anchor: null }))

		expect(resource.type).toBe('reminder_list')
		expect(resource.anchor).toBeUndefined()
		expect(resource.href).toBe('/reminders/lists/reminder_list_1')
	})

	it('routes a calendar hit to the calendar and carries the matched event', () => {
		const resource = searchResultToResource(
			makeSearchResult({
				type: 'calendar',
				id: 'calendar_1',
				anchor: { type: 'calendar_event', id: 'calendar_event_1' },
			})
		)

		expect(resource.type).toBe('calendar')
		expect(resource.anchor).toEqual({ type: 'calendar_event', id: 'calendar_event_1' })
		expect(resource.href).toBe('/calendar?event=calendar_event_1&calendar=calendar_1')
	})

	it('routes a calendar hit on the calendar name with no focus', () => {
		const resource = searchResultToResource(
			makeSearchResult({ type: 'calendar', id: 'calendar_1', anchor: null })
		)

		expect(resource.anchor).toBeUndefined()
		expect(resource.href).toBe('/calendar')
	})

	it('focuses the matched message when a thread hit came from content', () => {
		const resource = searchResultToResource(
			makeSearchResult({
				type: 'thread',
				id: 'thread_1',
				anchor: { type: 'message', id: 'message_1' },
			})
		)

		expect(resource.href).toBe('/c/thread_1?message=message_1')
	})
})
