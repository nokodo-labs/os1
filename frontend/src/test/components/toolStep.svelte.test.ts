import ToolStep from '$lib/components/chat/tools/ToolStep.svelte'
import type { ToolExecution } from '$lib/tools'
import { fireEvent, render } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

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

/** renders a row and opens its collapsible body. */
async function expand(execution: ToolExecution): Promise<HTMLElement> {
	const { container } = render(ToolStep, { props: { execution } })
	const toggle = container.querySelector('button')
	expect(toggle).not.toBeNull()
	if (toggle) await fireEvent.click(toggle)
	return container
}

const event = {
	id: 'calendar_event_01a',
	title: 'dentist',
	start_at: '2026-09-01T09:00:00+00:00',
	end_at: '2026-09-01T10:00:00+00:00',
	calendar_id: 'calendar_01a',
}

describe('ToolStep calendar event results', () => {
	it('renders a direct calendar event read as a calendar row, not raw output', async () => {
		const container = await expand(
			done(
				'calendar_event_get',
				{ calendar_event_id: 'calendar_event_01a' },
				{ status: 'success', message: 'calendar event retrieved', event }
			)
		)

		expect(container.textContent).toContain('read dentist')
		const link = container.querySelector('a')
		expect(link?.getAttribute('href')).toBe('/calendar')
		expect(link?.textContent).toContain('dentist')
		expect(container.textContent).not.toContain('calendar_event_01a')
		expect(container.textContent).not.toContain('start_at')
	})

	it('renders the upcoming window as one row per scheduled item', async () => {
		const container = await expand(
			done(
				'calendar_event_get',
				{},
				{
					status: 'success',
					count: 2,
					results: [
						{
							type: 'calendar_event',
							id: 'calendar_event_01a',
							calendar_event_id: 'calendar_event_01a',
							title: 'standup',
							effective_start_at: '2026-09-01T09:00:00+00:00',
						},
						{
							type: 'reminder',
							id: 'reminder_01a',
							reminder_id: 'reminder_01a',
							title: 'buy milk',
							effective_start_at: '2026-09-01T18:00:00+00:00',
						},
					],
				}
			)
		)

		const links = Array.from(container.querySelectorAll('a'))
		expect(links).toHaveLength(2)
		expect(links[0]?.textContent).toContain('standup')
		expect(links[0]?.getAttribute('href')).toBe('/calendar')
		expect(links[1]?.textContent).toContain('buy milk')
		expect(links[1]?.getAttribute('href')).toBe('/reminders')
	})

	it('renders a created event through the calendar body', async () => {
		const container = await expand(
			done(
				'calendar_event_write',
				{ title: 'dentist' },
				{ status: 'success', message: 'calendar event created', event }
			)
		)

		expect(container.textContent).toContain('created dentist')
		expect(container.querySelector('a')?.getAttribute('href')).toBe('/calendar')
	})

	it('names the kind instead of an id when a calendar result carries no event', async () => {
		const container = await expand(
			done(
				'calendar_event_write',
				{ calendar_event_id: 'calendar_event_01a', delete: true },
				{ status: 'success', message: 'calendar event deleted', id: 'calendar_event_01a' }
			)
		)

		expect(container.textContent).toContain('deleted calendar event')
		expect(container.textContent).not.toContain('calendar_event_01a')
		expect(container.querySelector('a')?.getAttribute('href')).toBe('/calendar')
	})
})

describe('ToolStep row wording', () => {
	it('says listed, not found, for a plain chat listing', () => {
		const { container } = render(ToolStep, {
			props: {
				execution: done(
					'chat_get',
					{ limit: 10 },
					{ status: 'success', message: 'found 10 chats', count: 10, results: [] }
				),
			},
		})

		expect(container.textContent).toContain('listed 10 chats')
		expect(container.textContent).not.toContain('found')
	})

	it('keeps found on a chat search', () => {
		const { container } = render(ToolStep, {
			props: {
				execution: done(
					'chat_get',
					{ query: 'tax' },
					{ status: 'success', count: 2, results: [] }
				),
			},
		})

		expect(container.textContent).toContain('found 2 chats')
		expect(container.textContent).toContain('tax')
	})
})
