import { buildRunBlocks, getBlockResponseItems } from '$lib/chat/helpers'
import { isFailureOutstanding, parseRunFailureEvent } from '$lib/chat/runFailures'
import type { ApiMessage, RunFailureEntry } from '$lib/chat/types'
import { describe, expect, it } from 'vitest'
import { makeApiMessage } from './fixtures'

const threadId = 'thread_1'
const userId = 'user_1'
const agentId = 'agent_1'

function at(seconds: number): string {
	return new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString()
}

function message(overrides: Partial<ApiMessage>): ApiMessage {
	return makeApiMessage({
		thread_id: threadId,
		created_at: at(0),
		updated_at: at(0),
		...overrides,
	})
}

function failure(overrides: Partial<RunFailureEntry> = {}): RunFailureEntry {
	return {
		id: 'event_1',
		threadId,
		agentId,
		reason: 'provider_error',
		runId: 'run_1',
		anchorMessageId: 'u1',
		partialMessageId: null,
		createdAt: new Date(at(5)),
		...overrides,
	}
}

describe('parseRunFailureEvent', () => {
	it('reads the durable event, taking the anchor from message_id', () => {
		const entry = parseRunFailureEvent({
			id: 'event_1',
			type: 'run.error',
			message_id: 'u1',
			created_at: at(5),
			data: {
				thread_id: threadId,
				agent_id: agentId,
				run_id: null,
				reason: 'never_started',
				partial_message_id: null,
			},
		})

		expect(entry).toMatchObject({
			id: 'event_1',
			agentId,
			reason: 'never_started',
			runId: null,
			anchorMessageId: 'u1',
		})
	})

	it('ignores events that are not run.error', () => {
		expect(
			parseRunFailureEvent({
				id: 'event_2',
				type: 'run.activity.progress',
				data: { thread_id: threadId, agent_id: agentId },
			})
		).toBeNull()
	})

	it('coerces a reason outside the closed enum instead of leaking it', () => {
		const entry = parseRunFailureEvent({
			id: 'event_3',
			type: 'run.error',
			message_id: 'u1',
			data: { thread_id: threadId, agent_id: agentId, reason: 'agent_unavailable' },
		})

		expect(entry?.reason).toBe('provider_error')
	})
})

describe('isFailureOutstanding', () => {
	it('stays outstanding while nothing answered the anchor', () => {
		expect(isFailureOutstanding(failure(), [])).toBe(true)
	})

	it('goes stale once the same agent answers that anchor afterwards', () => {
		const answer = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: agentId,
			reply_to_message_id: 'u1',
			created_at: at(9),
		})

		expect(isFailureOutstanding(failure(), [answer])).toBe(false)
	})

	it('goes stale when a retry answers the anchor structurally', () => {
		// a retry is spliced ONTO the anchor and carries no reply pointer
		const retried = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: agentId,
			parent_id: 'u1',
			reply_to_message_id: null,
			created_at: at(9),
		})

		expect(isFailureOutstanding(failure(), [retried])).toBe(false)
	})

	it('ignores the run\u2019s own partial output', () => {
		const partial = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: agentId,
			reply_to_message_id: 'u1',
			created_at: at(9),
		})

		expect(isFailureOutstanding(failure({ partialMessageId: 'a1' }), [partial])).toBe(true)
	})

	it('goes stale when the answer names its agent only in metadata', () => {
		// the column is not the only place the agent id lives, so matching it
		// alone left every failure outstanding and the answered-later state
		// unreachable.
		const answer = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: null,
			metadata: { agent_id: agentId },
			reply_to_message_id: 'u1',
			created_at: at(9),
		})

		expect(isFailureOutstanding(failure(), [answer])).toBe(false)
	})

	it('is not settled by a different agent answering the same anchor', () => {
		const other = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: 'agent_2',
			reply_to_message_id: 'u1',
			created_at: at(9),
		})

		expect(isFailureOutstanding(failure(), [other])).toBe(true)
	})
})

describe('buildRunBlocks run failures', () => {
	it('renders a never_started failure that has no assistant block', () => {
		const user = message({
			id: 'u1',
			type: 'user',
			sender_user_id: userId,
			created_at: at(1),
		})

		const { blocks } = buildRunBlocks({
			messages: [user],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: false,
			runFailures: [failure({ reason: 'never_started', runId: null })],
		})

		const items = blocks.flatMap((block) => getBlockResponseItems(block))
		expect(items).toHaveLength(1)
		expect(items[0]).toMatchObject({ kind: 'run_failure' })
	})

	it('shows only the newest failure when several stack on one anchor', () => {
		const user = message({
			id: 'u1',
			type: 'user',
			sender_user_id: userId,
			created_at: at(1),
		})

		const { blocks } = buildRunBlocks({
			messages: [user],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: false,
			runFailures: [
				failure({ id: 'event_late', createdAt: new Date(at(9)) }),
				failure({ id: 'event_early', createdAt: new Date(at(3)) }),
			],
		})

		const ids = blocks
			.flatMap((block) => getBlockResponseItems(block))
			.filter((item) => item.kind === 'run_failure')
			.map((item) => (item.kind === 'run_failure' ? item.failure.id : null))

		// retrying any of them re-answers the same anchor, so stacking them
		// would offer several buttons that all do the identical thing
		expect(ids).toEqual(['event_late'])
	})

	it('keeps failures from different agents on the same anchor', () => {
		const user = message({
			id: 'u1',
			type: 'user',
			sender_user_id: userId,
			created_at: at(1),
		})

		const { blocks } = buildRunBlocks({
			messages: [user],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: false,
			runFailures: [
				failure({ id: 'event_a', agentId: 'agent_1', createdAt: new Date(at(3)) }),
				failure({ id: 'event_b', agentId: 'agent_2', createdAt: new Date(at(4)) }),
			],
		})

		const ids = blocks
			.flatMap((block) => getBlockResponseItems(block))
			.filter((item) => item.kind === 'run_failure')
			.map((item) => (item.kind === 'run_failure' ? item.failure.id : null))

		expect(ids).toEqual(['event_a', 'event_b'])
	})

	it('renders the failure inside the answering block, not one of its own', () => {
		const user = message({
			id: 'u1',
			type: 'user',
			sender_user_id: userId,
			created_at: at(1),
		})
		const answer = message({
			id: 'a1',
			type: 'assistant',
			sender_agent_id: agentId,
			parent_id: 'u1',
			content: [{ type: 'text', text: 'recovered' }],
			metadata: { run_id: 'run_1' },
			created_at: at(9),
		})

		const { blocks } = buildRunBlocks({
			messages: [user, answer],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: false,
			runFailures: [failure()],
		})

		// one block holds BOTH the failure and the answer that followed it
		const withFailure = blocks.filter((b) => b.items.some((i) => i.kind === 'run_failure'))
		expect(withFailure).toHaveLength(1)
		const kinds = withFailure[0].items.map((i) => i.kind)
		expect(kinds).toContain('run_failure')
		expect(kinds).toContain('assistant')
		// and it is attributed to the agent, never the bare "assistant" fallback
		expect(withFailure[0].agentId).toBe(agentId)
	})

	it('drops a failure whose anchor is not on the loaded branch', () => {
		const user = message({
			id: 'u1',
			type: 'user',
			sender_user_id: userId,
			created_at: at(1),
		})

		const { blocks } = buildRunBlocks({
			messages: [user],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: false,
			runFailures: [failure({ anchorMessageId: 'other_branch_message' })],
		})

		const items = blocks.flatMap((block) => getBlockResponseItems(block))
		expect(items).toHaveLength(0)
	})
})
