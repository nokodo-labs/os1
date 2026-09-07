import type { components } from '$lib/api/types'
import {
	buildReminderListExport,
	buildReminderListMarkdown,
	groupRemindersForExport,
	type ExportableReminder,
} from '$lib/reminders/export'
import { describe, expect, it } from 'vitest'

type ApiReminder = components['schemas']['Reminder']
type ApiReminderWithSubtasks = components['schemas']['ReminderWithSubtasks']
type ApiReminderList = components['schemas']['ReminderList']

function makeReminder(overrides: Partial<ApiReminder> & { id: string }): ApiReminder {
	return {
		id: overrides.id,
		owner_id: 'user_1',
		list_id: overrides.list_id ?? 'list_1',
		parent_id: overrides.parent_id ?? null,
		title: overrides.title ?? `reminder ${overrides.id}`,
		description: overrides.description ?? null,
		status: overrides.status ?? 'pending',
		position: overrides.position ?? 0,
		due_at: overrides.due_at ?? null,
		remind_at: overrides.remind_at ?? null,
		completed_at: overrides.completed_at ?? null,
		created_at: '2026-08-01T10:00:00Z',
		updated_at: '2026-08-02T10:00:00Z',
		recurrence: overrides.recurrence ?? null,
		recurrence_until: overrides.recurrence_until ?? null,
		series_origin_id: null,
		origin_message_id: null,
	}
}

function withSubtasks(reminder: ApiReminder, subtasks: ApiReminder[]): ApiReminderWithSubtasks {
	return { ...reminder, subtasks }
}

const list: ApiReminderList = {
	id: 'list_1',
	owner_id: 'user_1',
	name: 'groceries',
	description: 'weekly run',
	color: '#ff0000',
	icon: '🛒',
	is_default: false,
	position: 0,
	origin_message_id: null,
	created_at: '2026-07-01T10:00:00Z',
	updated_at: '2026-07-02T10:00:00Z',
}

describe('reminder list export', () => {
	it('keeps completed reminders in their own group', () => {
		const items: ExportableReminder[] = [
			makeReminder({ id: 'a', title: 'milk', position: 0 }),
			makeReminder({
				id: 'b',
				title: 'bread',
				status: 'completed',
				completed_at: '2026-08-03T10:00:00Z',
				position: 1,
			}),
			makeReminder({ id: 'c', title: 'eggs', position: 2 }),
		]

		const group = groupRemindersForExport(items)

		expect(group.pending.map((item) => item.title)).toEqual(['milk', 'eggs'])
		expect(group.completed.map((item) => item.title)).toEqual(['bread'])
		expect(group.completed[0].completed_at).toBe('2026-08-03T10:00:00Z')
	})

	it('orders each group by position', () => {
		const group = groupRemindersForExport([
			makeReminder({ id: 'a', title: 'third', position: 2 }),
			makeReminder({ id: 'b', title: 'first', position: 0 }),
			makeReminder({ id: 'c', title: 'second', position: 1 }),
		])

		expect(group.pending.map((item) => item.title)).toEqual(['first', 'second', 'third'])
	})

	it('nests sub-reminders and splits them by completion too', () => {
		const parent = withSubtasks(makeReminder({ id: 'p', title: 'party' }), [
			makeReminder({ id: 's1', title: 'cake', parent_id: 'p', position: 0 }),
			makeReminder({
				id: 's2',
				title: 'invites',
				parent_id: 'p',
				status: 'completed',
				position: 1,
			}),
		])

		const group = groupRemindersForExport([parent])
		const exported = group.pending[0]

		expect(exported.subtasks.pending.map((item) => item.title)).toEqual(['cake'])
		expect(exported.subtasks.completed.map((item) => item.title)).toEqual(['invites'])
		expect(exported.subtasks.pending[0].parent_id).toBe('p')
		expect(exported.subtasks.pending[0].subtasks).toEqual({ pending: [], completed: [] })
	})

	it('emits structured fields per reminder instead of a markdown blob', () => {
		const group = groupRemindersForExport([
			makeReminder({
				id: 'a',
				title: 'water the plants',
				description: 'balcony only',
				due_at: '2026-09-01T08:00:00Z',
				remind_at: '2026-09-01T07:30:00Z',
				recurrence: { rrule: ['FREQ=WEEKLY'], timezone: 'Europe/Rome' },
				recurrence_until: '2026-12-01T08:00:00Z',
			}),
		])

		expect(group.pending[0]).toEqual({
			id: 'a',
			list_id: 'list_1',
			parent_id: null,
			title: 'water the plants',
			description: 'balcony only',
			status: 'pending',
			position: 0,
			due_at: '2026-09-01T08:00:00Z',
			remind_at: '2026-09-01T07:30:00Z',
			completed_at: null,
			created_at: '2026-08-01T10:00:00Z',
			updated_at: '2026-08-02T10:00:00Z',
			recurrence: { rrule: ['FREQ=WEEKLY'], timezone: 'Europe/Rome' },
			recurrence_until: '2026-12-01T08:00:00Z',
			subtasks: { pending: [], completed: [] },
		})
		expect(Object.keys(group.pending[0])).not.toContain('markdown')
	})

	it('counts every level of the tree', () => {
		const data = buildReminderListExport(list, [
			withSubtasks(makeReminder({ id: 'p', title: 'party' }), [
				makeReminder({ id: 's1', title: 'cake', parent_id: 'p' }),
				makeReminder({ id: 's2', title: 'invites', parent_id: 'p', status: 'completed' }),
			]),
			makeReminder({ id: 'done', title: 'old', status: 'completed' }),
		])

		expect(data.counts).toEqual({ total: 4, pending: 2, completed: 2 })
		expect(data.list?.name).toBe('groceries')
		expect(data.list?.icon).toBe('🛒')
	})

	it('exports a null list when the list is unknown', () => {
		const data = buildReminderListExport(null, [])
		expect(data.list).toBeNull()
		expect(data.reminders).toEqual({ pending: [], completed: [] })
		expect(data.counts).toEqual({ total: 0, pending: 0, completed: 0 })
	})

	it('renders markdown with a separate completed section', () => {
		const data = buildReminderListExport(list, [
			withSubtasks(makeReminder({ id: 'p', title: 'party' }), [
				makeReminder({ id: 's1', title: 'cake', parent_id: 'p' }),
			]),
			makeReminder({ id: 'done', title: 'old thing', status: 'completed' }),
		])

		const markdown = buildReminderListMarkdown({
			title: 'groceries',
			url: 'https://nokodo.test/reminders/lists/list_1',
			data,
		})

		expect(markdown).toContain('# groceries')
		expect(markdown).toContain('link: https://nokodo.test/reminders/lists/list_1')
		expect(markdown).toContain('## reminders')
		expect(markdown).toContain('## completed')
		expect(markdown).toContain('- [ ] party')
		expect(markdown).toContain('  - [ ] cake')
		expect(markdown).toContain('- [x] old thing')
		expect(markdown.indexOf('- [ ] party')).toBeLessThan(markdown.indexOf('## completed'))
	})

	it('omits empty markdown sections', () => {
		const markdown = buildReminderListMarkdown({
			title: 'groceries',
			url: 'https://nokodo.test/reminders/lists/list_1',
			data: buildReminderListExport(list, [makeReminder({ id: 'a', title: 'milk' })]),
		})

		expect(markdown).toContain('## reminders')
		expect(markdown).not.toContain('## completed')
		expect(markdown).toContain('completed: 0')
	})
})
