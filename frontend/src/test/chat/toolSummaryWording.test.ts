import { getToolSummary, type ToolExecution } from '$lib/tools'
import { describe, expect, it } from 'vitest'

/**
 * "found" is a claim about searching. a tool that fetched one resource by id,
 * or paged through a plain listing, found nothing - it read what was there.
 */

function done(
	name: string,
	args: Record<string, unknown>,
	output: Record<string, unknown>
): ToolExecution {
	return {
		toolCall: { id: 'call_1', name, arguments: args },
		status: 'completed',
		events: [],
		result: { toolCallId: 'call_1', output: JSON.stringify(output), isError: false },
	}
}

function running(name: string, args: Record<string, unknown>): ToolExecution {
	return { toolCall: { id: 'call_1', name, arguments: args }, status: 'running', events: [] }
}

function title(execution: ToolExecution): string {
	return getToolSummary(execution).title
}

describe('tool summary wording: direct gets never say found', () => {
	it('reads one chat by id', () => {
		const summary = getToolSummary(
			done(
				'chat_get',
				{ chat_id: 'thread_01a' },
				{ status: 'success', chat: { chat_id: 'thread_01a', title: 'grocery run' } }
			)
		)
		expect(summary.title).toBe('read grocery run')
		expect(summary.resourceType).toBe('chat')
	})

	it('reads one note by id', () => {
		expect(
			title(
				done('note_get', { note_id: 'note_01a' }, { status: 'success', title: 'recipes' })
			)
		).toBe('read recipes')
	})

	it('reads one file by id', () => {
		expect(
			title(
				done('file_get', { file_id: 'file_01a' }, { status: 'success', filename: 'cv.pdf' })
			)
		).toBe('read cv.pdf')
	})

	it('checks one project by id', () => {
		expect(
			title(
				done(
					'project_get',
					{ project_id: 'project_01a' },
					{ status: 'success', name: 'os1' }
				)
			)
		).toBe('checked os1')
	})

	it('checks one reminder by id', () => {
		expect(
			title(
				done(
					'reminder_get',
					{ reminder_id: 'reminder_01a' },
					{ status: 'success', reminder: { title: 'buy milk' } }
				)
			)
		).toBe('checked buy milk')
	})

	it('reads one calendar event by id', () => {
		expect(
			title(
				done(
					'calendar_event_get',
					{ calendar_event_id: 'calendar_event_01a' },
					{ status: 'success', event: { id: 'calendar_event_01a', title: 'dentist' } }
				)
			)
		).toBe('read dentist')
	})
})

describe('tool summary wording: listings say listed, not found', () => {
	it('lists chats', () => {
		expect(title(done('chat_get', { limit: 10 }, { status: 'success', count: 10 }))).toBe(
			'listed 10 chats'
		)
		expect(title(done('chat_get', {}, { status: 'success', count: 1 }))).toBe('listed 1 chat')
		expect(title(done('chat_get', {}, { status: 'success', count: 0 }))).toBe('no chats')
	})

	it('lists files', () => {
		expect(title(running('file_get', {}))).toBe('listing files')
		expect(title(done('file_get', {}, { status: 'success', count: 4 }))).toBe('listed 4 files')
		expect(title(done('file_get', {}, { status: 'success', count: 0 }))).toBe('no files')
	})

	it('lists reminder lists', () => {
		expect(title(running('reminder_get', {}))).toBe('listing reminder lists')
		expect(title(done('reminder_get', {}, { status: 'success', count: 3 }))).toBe(
			'listed 3 reminder lists'
		)
		expect(title(done('reminder_get', {}, { status: 'success', count: 0 }))).toBe(
			'no reminder lists'
		)
	})

	it('lists the upcoming calendar window', () => {
		expect(title(running('calendar_event_get', {}))).toBe('checking what is coming up')
		expect(title(done('calendar_event_get', {}, { status: 'success', count: 2 }))).toBe(
			'2 scheduled items coming up'
		)
		expect(title(done('calendar_event_get', {}, { status: 'success', count: 1 }))).toBe(
			'1 scheduled item coming up'
		)
		expect(title(done('calendar_event_get', {}, { status: 'success', count: 0 }))).toBe(
			'nothing coming up'
		)
	})

	it('never says found for a get or a listing', () => {
		const gets: ToolExecution[] = [
			done('chat_get', { chat_id: 'thread_01a' }, { status: 'success', chat: {} }),
			done('note_get', { note_id: 'note_01a' }, { status: 'success' }),
			done('file_get', { file_id: 'file_01a' }, { status: 'success' }),
			done('project_get', { project_id: 'project_01a' }, { status: 'success' }),
			done('reminder_get', { reminder_id: 'reminder_01a' }, { status: 'success' }),
			done('reminder_get', { list_id: 'reminder_list_01a' }, { status: 'success' }),
			done(
				'calendar_event_get',
				{ calendar_event_id: 'calendar_event_01a' },
				{ status: 'success' }
			),
			done('chat_get', {}, { status: 'success', count: 7 }),
			done('file_get', {}, { status: 'success', count: 7 }),
			done('reminder_get', {}, { status: 'success', count: 7 }),
			done('calendar_event_get', {}, { status: 'success', count: 7 }),
		]
		for (const execution of gets) {
			expect(title(execution)).not.toContain('found')
		}
	})
})

describe('tool summary wording: searches keep found', () => {
	it('keeps found for every search that really searched', () => {
		expect(title(done('chat_get', { query: 'tax' }, { status: 'success', count: 3 }))).toBe(
			'found 3 chats'
		)
		expect(title(done('note_get', { query: 'tax' }, { status: 'success', count: 1 }))).toBe(
			'found 1 note'
		)
		expect(title(done('file_get', { query: 'tax' }, { status: 'success', count: 2 }))).toBe(
			'found 2 files'
		)
		expect(title(done('project_get', { query: 'tax' }, { status: 'success', count: 2 }))).toBe(
			'found 2 projects'
		)
		expect(
			title(done('calendar_event_get', { query: 'tax' }, { status: 'success', count: 2 }))
		).toBe('found 2 calendar events')
		expect(
			title(
				done(
					'reminder_get',
					{ query: 'tax' },
					{ status: 'success', list_count: 1, reminder_count: 2 }
				)
			)
		).toBe('found 3 reminder results')
		expect(
			title(done('resource_search', { query: 'tax' }, { status: 'success', count: 5 }))
		).toBe('found 5 resources')
	})

	it('carries the query as the subtitle of a search', () => {
		const summary = getToolSummary(
			done('file_get', { query: 'invoice' }, { status: 'success', count: 2 })
		)
		expect(summary.subtitle).toBe('invoice')
	})

	it('leaves a listing without a query subtitle', () => {
		expect(getToolSummary(done('file_get', {}, { status: 'success', count: 2 })).subtitle).toBe(
			undefined
		)
	})
})
