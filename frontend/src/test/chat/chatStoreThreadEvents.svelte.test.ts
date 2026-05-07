/**
 * tests for ChatStore thread event handling in chat.svelte.ts.
 * validates that thread.created, thread.updated, thread.deleted, and thread.read
 * events correctly update recentThreads, activeThread, and threadCache.
 *
 * uses .svelte.test.ts so Svelte 5 runes ($state) work in the test runtime.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeStreamMessage, makeThread, resetIdCounter } from './fixtures'

// --- module mocks (must be before imports that use them) ---

// capture the handler registered via eventStreamClient.subscribe
let capturedHandler: ((msg: unknown) => void) | null = null

vi.mock('$lib/api/streaming', () => ({
	eventStreamClient: {
		subscribe: vi.fn((handler: (msg: unknown) => void) => {
			capturedHandler = handler
			return () => {
				capturedHandler = null
			}
		}),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null, response: { status: 204 } }),
	},
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/auth/jwt', () => ({
	getJwtUserId: vi.fn(() => 'user_test'),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		init: vi.fn(),
		cleanup: vi.fn(),
	},
}))

// --- import the module under test after mocks are set up ---

import { chat } from '$lib/stores/chat.svelte'

/** dispatch one event through the store's handler */
function dispatch(msg: unknown): void {
	if (!capturedHandler) throw new Error('no handler registered - did you call chat.init()?')
	capturedHandler(msg)
}

describe('ChatStore thread event handling', () => {
	beforeEach(() => {
		resetIdCounter()
		chat.clear()
		chat.init()
	})

	afterEach(() => {
		chat.cleanup()
		capturedHandler = null
	})

	// -- thread.created --

	describe('thread.created', () => {
		it('prepends a new thread to recentThreads', () => {
			const thread = makeThread({ id: 't1', title: 'new thread' })
			dispatch(makeStreamMessage('thread.created', { ...thread }))

			expect(chat.recentThreads).toHaveLength(1)
			expect(chat.recentThreads[0].id).toBe('t1')
			expect(chat.recentThreads[0].title).toBe('new thread')
		})

		it('deduplicates if thread already exists', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('thread.created', { ...thread }))

			expect(chat.recentThreads).toHaveLength(1)
		})

		it('ignores temporary threads', () => {
			const thread = makeThread({ id: 't1', is_temporary: true })
			dispatch(makeStreamMessage('thread.created', { ...thread }))

			expect(chat.recentThreads).toHaveLength(0)
		})

		it('ignores events with no data', () => {
			dispatch({ type: 'thread.created' })
			expect(chat.recentThreads).toHaveLength(0)
		})

		it('caches the thread', () => {
			const thread = makeThread({ id: 't1' })
			dispatch(makeStreamMessage('thread.created', { ...thread }))

			expect(chat.threadCache.get('t1')).not.toBeNull()
		})
	})

	// -- thread.updated --

	describe('thread.updated', () => {
		it('updates title in recentThreads', () => {
			const thread = makeThread({ id: 't1', title: 'old title' })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'new title',
					updated_at: new Date().toISOString(),
				})
			)

			expect(chat.recentThreads[0].title).toBe('new title')
		})

		it('updates tags in recentThreads', () => {
			const thread = makeThread({ id: 't1', tags: ['old'] })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					tags: ['new', 'tags'],
					updated_at: new Date().toISOString(),
				})
			)

			expect(chat.recentThreads[0].tags).toEqual(['new', 'tags'])
		})

		it('filters non-string tags', () => {
			const thread = makeThread({ id: 't1', tags: [] })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					tags: ['valid', 123, null, 'also-valid'],
				})
			)

			expect(chat.recentThreads[0].tags).toEqual(['valid', 'also-valid'])
		})

		it('updates activeThread when it matches', () => {
			const thread = makeThread({ id: 't1', title: 'old' })
			chat.activeThread = thread

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'updated title',
				})
			)

			expect(chat.activeThread?.title).toBe('updated title')
		})

		it('does not touch activeThread when id does not match', () => {
			const thread = makeThread({ id: 't1', title: 'original' })
			chat.activeThread = thread

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't2',
					title: 'other',
				})
			)

			expect(chat.activeThread?.title).toBe('original')
		})

		it('updates last_activity_at and updated_at', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]
			const ts = '2026-04-03T12:00:00.000Z'

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					last_activity_at: ts,
					updated_at: ts,
				})
			)

			expect(chat.recentThreads[0].last_activity_at).toBe(ts)
			expect(chat.recentThreads[0].updated_at).toBe(ts)
		})

		it('only applies known fields (does not spread arbitrary data)', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'ok',
					_unknown_field: 'should not appear',
					random_number: 42,
				})
			)

			const updated = chat.recentThreads[0] as Record<string, unknown>
			expect(updated.title).toBe('ok')
			expect(updated._unknown_field).toBeUndefined()
			expect(updated.random_number).toBeUndefined()
		})

		it('updates is_archived flag', () => {
			const thread = makeThread({ id: 't1', is_archived: false })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					is_archived: true,
				})
			)

			expect(chat.recentThreads[0].is_archived).toBe(true)
		})

		it('merges into thread cache when cached', () => {
			const thread = makeThread({ id: 't1', title: 'cached' })
			chat.threadCache.set(thread)

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'updated',
				})
			)

			expect(chat.threadCache.get('t1')?.title).toBe('updated')
		})

		it('invalidates cache when thread was not cached', () => {
			// no thread in cache
			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'something',
				})
			)

			// should not throw, and cache should remain empty
			expect(chat.threadCache.get('t1')).toBeNull()
		})

		it('ignores event with no threadId', () => {
			const thread = makeThread({ id: 't1', title: 'original' })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('thread.updated', {}))

			expect(chat.recentThreads[0].title).toBe('original')
		})

		it('preserves unchanged fields when only timestamps are sent', () => {
			const thread = makeThread({ id: 't1', title: 'my chat', tags: ['a', 'b'] })
			chat.recentThreads = [thread]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					last_activity_at: new Date().toISOString(),
					updated_at: new Date().toISOString(),
				})
			)

			expect(chat.recentThreads[0].title).toBe('my chat')
			expect(chat.recentThreads[0].tags).toEqual(['a', 'b'])
		})

		it('promotes updated thread to top of recentThreads', () => {
			const t1 = makeThread({ id: 't1', title: 'first' })
			const t2 = makeThread({ id: 't2', title: 'second' })
			chat.recentThreads = [t1, t2]

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't2',
					title: 'now first',
				})
			)

			expect(chat.recentThreads[0].id).toBe('t2')
			expect(chat.recentThreads[1].id).toBe('t1')
		})
	})

	// -- thread.deleted --

	describe('thread.deleted', () => {
		it('removes thread from recentThreads', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('thread.deleted', { id: 't1' }))

			expect(chat.recentThreads).toHaveLength(0)
		})

		it('nulls activeThread when it matches', () => {
			const thread = makeThread({ id: 't1' })
			chat.activeThread = thread

			dispatch(makeStreamMessage('thread.deleted', { id: 't1' }))

			expect(chat.activeThread).toBeNull()
		})

		it('does not null activeThread for a different thread', () => {
			const thread = makeThread({ id: 't1' })
			chat.activeThread = thread

			dispatch(makeStreamMessage('thread.deleted', { id: 't2' }))

			expect(chat.activeThread?.id).toBe('t1')
		})

		it('invalidates thread cache', () => {
			const thread = makeThread({ id: 't1' })
			chat.threadCache.set(thread)

			dispatch(makeStreamMessage('thread.deleted', { id: 't1' }))

			expect(chat.threadCache.get('t1')).toBeNull()
		})

		it('ignores event with no threadId', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('thread.deleted', {}))

			expect(chat.recentThreads).toHaveLength(1)
		})
	})

	// -- thread.read --

	describe('thread.read', () => {
		it('clears unread count for the thread', () => {
			chat.unreadCounts.set('t1', 5)

			dispatch(makeStreamMessage('thread.read', { thread_id: 't1' }))

			expect(chat.unreadCounts.has('t1')).toBe(false)
		})

		it('ignores events for unknown threads', () => {
			chat.unreadCounts.set('t1', 5)

			dispatch(makeStreamMessage('thread.read', { thread_id: 't2' }))

			expect(chat.unreadCounts.get('t1')).toBe(5)
		})
	})

	// -- message.created unread state --

	describe('message.created unread state', () => {
		it('marks assistant messages unread when the thread is not active', () => {
			const message = makeApiMessage({ id: 'm1', thread_id: 't1', type: 'assistant' })

			dispatch(makeStreamMessage('message.created', { ...message, thread_id: 't1' }))

			expect(chat.unreadCounts.get('t1')).toBe(1)
		})

		it('marks tool messages unread', () => {
			const message = makeApiMessage({ id: 'm1', thread_id: 't1', type: 'tool' })

			dispatch(makeStreamMessage('message.created', { ...message, thread_id: 't1' }))

			expect(chat.unreadCounts.get('t1')).toBe(1)
		})
	})

	// -- post-run metadata generation state --

	describe('thread metadata generation state', () => {
		it('does not mark missing metadata generating after a run completes', () => {
			const thread = makeThread({ id: 't1', title: null, tags: [] })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('run.completed', { thread_id: 't1', run_id: 'run_1' }))

			expect(chat.metadataGeneratingThreadIds.has('t1')).toBe(false)

			dispatch(
				makeStreamMessage('thread.updated', {
					id: 't1',
					title: 'generated title',
					tags: ['generated'],
				})
			)

			expect(chat.metadataGeneratingThreadIds.has('t1')).toBe(false)
		})

		it('tracks active thread maintenance tasks', () => {
			const task = {
				id: 'task_1',
				user_id: 'user_1',
				task_type: 'custom',
				status: 'running',
				progress: 0,
				metadata_: { task_name: 'thread.maintenance', thread_id: 't1' },
				spawned_thread_id: 't1',
				created_at: new Date().toISOString(),
				updated_at: new Date().toISOString(),
			}

			dispatch(makeStreamMessage('task.created', { task }))

			expect(chat.metadataGeneratingThreadIds.has('t1')).toBe(true)

			dispatch(makeStreamMessage('task.failed', { task }))

			expect(chat.metadataGeneratingThreadIds.has('t1')).toBe(false)
		})
	})

	// -- edge cases --

	describe('edge cases', () => {
		it('ignores events with no data', () => {
			dispatch({ type: 'thread.updated' })
			dispatch({ type: 'thread.deleted' })
			dispatch({ type: 'thread.created' })
			expect(chat.recentThreads).toHaveLength(0)
		})

		it('ignores unknown event types', () => {
			const thread = makeThread({ id: 't1' })
			chat.recentThreads = [thread]

			dispatch(makeStreamMessage('thread.unknown-type', { id: 't1' }))

			expect(chat.recentThreads).toHaveLength(1)
		})
	})
})
