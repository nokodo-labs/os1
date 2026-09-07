/**
 * export options are declared per resource type and read back through the
 * snapshot builders. the thread scope is the only declared option so far, so
 * these cover the registry contract and the path its value takes into a request.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getThread, getBranchMessages, getAllMessages } = vi.hoisted(() => ({
	getThread: vi.fn(),
	getBranchMessages: vi.fn(),
	getAllMessages: vi.fn(),
}))

vi.mock('$lib/stores/chat.svelte', () => ({
	chat: { threadCache: { getThread, getBranchMessages, getAllMessages } },
}))
vi.mock('$lib/stores/calendars.svelte', () => ({ calendars: { load: vi.fn(), all: [] } }))
vi.mock('$lib/stores/files.svelte', () => ({ files: { load: vi.fn(), get: () => null } }))
vi.mock('$lib/stores/groups.svelte', () => ({ groups: { load: vi.fn(), getById: () => null } }))
vi.mock('$lib/stores/notes.svelte', () => ({ notes: { load: vi.fn(), get: () => null } }))
vi.mock('$lib/stores/projects.svelte', () => ({ projects: { load: vi.fn(), getById: () => null } }))
vi.mock('$lib/stores/reminders.svelte', () => ({
	reminders: { loadLists: vi.fn(), getListById: () => null, loadReminders: vi.fn() },
}))

import {
	BASE_EXPORT_OPTION_VALUES,
	defaultExportOptionValues,
	exportOptionsFor,
	toThreadExportScope,
} from '$lib/components/share/exportOptions'
import { buildResourceSnapshot } from '$lib/components/share/shareSnapshots'
import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'

const threadPayload: ResourceAccessPayload = {
	resourceType: 'thread',
	resourceId: 'thread_1',
	title: 'a chat',
}

function message(id: string, text: string) {
	return { id, type: 'user', content: [{ type: 'text', text }] }
}

describe('export option registry', () => {
	it('declares a single-choice scope option for threads only', () => {
		const definitions = exportOptionsFor('thread')
		expect(definitions).toHaveLength(1)
		expect(definitions[0].kind).toBe('single-choice')
		expect(definitions[0].choices.map((choice) => choice.id)).toEqual(['branch', 'tree'])
		expect(exportOptionsFor('note')).toHaveLength(0)
		expect(exportOptionsFor(undefined)).toHaveLength(0)
	})

	it('gives every option and every choice an icon', () => {
		for (const definition of exportOptionsFor('thread')) {
			expect(definition.icon).toBeTruthy()
			for (const choice of definition.choices) expect(choice.icon).toBeTruthy()
		}
	})

	it('seeds values from the declared defaults', () => {
		expect(defaultExportOptionValues('thread')).toEqual({ threadScope: 'branch' })
		expect(defaultExportOptionValues('note')).toEqual(BASE_EXPORT_OPTION_VALUES)
	})

	it('reads and writes only its own field of the values record', () => {
		const [scope] = exportOptionsFor('thread')
		const values = defaultExportOptionValues('thread')
		expect(scope.read(values)).toBe('branch')

		const updated = scope.write(values, 'tree')
		expect(scope.read(updated)).toBe('tree')
		expect(values.threadScope).toBe('branch')

		expect(scope.read(scope.write(values, 'nonsense'))).toBe('branch')
		expect(toThreadExportScope('tree')).toBe('tree')
	})
})

describe('option values reaching the snapshot request', () => {
	beforeEach(() => {
		vi.clearAllMocks()
		getThread.mockResolvedValue({ id: 'thread_1', title: 'a chat' })
		getBranchMessages.mockResolvedValue([message('m1', 'on the branch')])
		getAllMessages.mockResolvedValue([message('m1', 'everywhere')])
	})

	it('takes the visible branch by default', async () => {
		const snapshot = await buildResourceSnapshot({
			payload: threadPayload,
			title: 'a chat',
			url: 'https://example.test/c/thread_1',
		})
		expect(getBranchMessages).toHaveBeenCalledWith('thread_1', 500)
		expect(getAllMessages).not.toHaveBeenCalled()
		expect(snapshot.json.export_scope).toBe('branch')
		expect(snapshot.markdown).toContain('on the branch')
	})

	it('takes every branch when the chosen value says so', async () => {
		const [scope] = exportOptionsFor('thread')
		const snapshot = await buildResourceSnapshot({
			payload: threadPayload,
			title: 'a chat',
			url: 'https://example.test/c/thread_1',
			options: scope.write(defaultExportOptionValues('thread'), 'tree'),
		})
		expect(getAllMessages).toHaveBeenCalledWith('thread_1', 500)
		expect(getBranchMessages).not.toHaveBeenCalled()
		expect(snapshot.json.export_scope).toBe('tree')
		expect(snapshot.markdown).toContain('everywhere')
	})
})
