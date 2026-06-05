import type { SearchResult } from '$lib/api/streaming'
import { searchResultToResource } from '$lib/resources/searchResults'
import { describe, expect, it } from 'vitest'

/** Build a minimal generated search result fixture. */
function makeSearchResult(overrides: Partial<SearchResult>): SearchResult {
	return {
		type: 'reminder',
		id: 'reminder_1',
		title: 'send draft',
		preview: null,
		created_at: '2025-01-01T00:00:00.000Z',
		updated_at: '2025-01-02T00:00:00.000Z',
		...overrides,
	}
}

describe('searchResultToResource', () => {
	it('uses generic parent references for reminder list routing', () => {
		const resource = searchResultToResource(
			makeSearchResult({
				parent: { type: 'reminder_list', id: 'reminder_list_1' },
			})
		)

		expect(resource.type).toBe('reminder')
		expect(resource.parent).toEqual({ type: 'reminder_list', id: 'reminder_list_1' })
		expect(resource.href).toBe('/reminders/lists/reminder_list_1')
	})

	it('falls back to the reminders route when a reminder parent is missing', () => {
		const resource = searchResultToResource(makeSearchResult({ parent: null }))

		expect(resource.type).toBe('reminder')
		expect(resource.parent).toBeUndefined()
		expect(resource.href).toBe('#')
	})

	it('keeps calendar event parent context without fabricating a deep link', () => {
		const resource = searchResultToResource(
			makeSearchResult({
				type: 'calendar_event',
				id: 'calendar_event_1',
				parent: { type: 'calendar', id: 'calendar_1' },
			})
		)

		expect(resource.type).toBe('calendar_event')
		expect(resource.parent).toEqual({ type: 'calendar', id: 'calendar_1' })
		expect(resource.href).toBe('#')
	})
})
