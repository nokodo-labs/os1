import { buildRunBlocks, getUserRunItemTimestamp } from '$lib/chat/helpers'
import type { ApiMessage, RunActivityState } from '$lib/chat/types'
import { describe, expect, it } from 'vitest'
import { makeApiMessage } from './fixtures'

const threadId = 'thread_1'
const userId = 'user_1'
const runId = 'run_1'
const agentId = 'agent_1'

function at(seconds: number): string {
	return new Date(Date.UTC(2026, 0, 1, 0, 0, seconds)).toISOString()
}

function message(overrides: Partial<ApiMessage>): ApiMessage {
	return makeApiMessage({
		thread_id: threadId,
		created_at: at(0),
		updated_at: at(0),
		metadata_: { run_id: runId },
		...overrides,
	})
}

describe('buildRunBlocks', () => {
	it('only timestamps the first same-author user item at the same time', () => {
		const timestamp = new Date('2026-01-01T00:00:00.000Z')
		const first = {
			kind: 'user' as const,
			align: 'right' as const,
			message: message({
				id: 'u1',
				type: 'user',
				sender_user_id: userId,
				created_at: timestamp.toISOString(),
			}),
		}
		const second = {
			kind: 'user' as const,
			align: 'right' as const,
			message: message({
				id: 'u2',
				type: 'user',
				sender_user_id: userId,
				created_at: timestamp.toISOString(),
			}),
		}

		expect(getUserRunItemTimestamp(first, undefined)).toEqual(timestamp)
		expect(getUserRunItemTimestamp(second, first)).toBeUndefined()
	})

	it('timestamps same-time user items from different authors', () => {
		const timestamp = new Date('2026-01-01T00:00:00.000Z')
		const first = {
			kind: 'user' as const,
			align: 'right' as const,
			message: message({
				id: 'u1',
				type: 'user',
				sender_user_id: 'user_1',
				created_at: timestamp.toISOString(),
			}),
		}
		const second = {
			kind: 'user' as const,
			align: 'left' as const,
			message: message({
				id: 'u2',
				type: 'user',
				sender_user_id: 'user_2',
				created_at: timestamp.toISOString(),
			}),
		}

		expect(getUserRunItemTimestamp(second, first)).toEqual(timestamp)
	})

	it('splits one backend run into visible turns after injected steering user messages', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'checking' }],
			tool_calls: [
				{
					id: 'tc_search',
					name: 'agentic_web_search',
					arguments: { query: 'news today' },
				},
			],
			created_at: at(2),
		})
		const toolResult = message({
			id: 't1',
			type: 'tool',
			parent_id: 'a1',
			sender_user_id: null,
			content: [{ type: 'text', text: 'search results' }],
			tool_call_id: 'tc_search',
			is_error: false,
			created_at: at(3),
		})
		const steeringUser = message({
			id: 'u2',
			type: 'user',
			parent_id: 't1',
			sender_user_id: userId,
			content: [{ type: 'text', text: 'in Iran I meant' }],
			metadata_: { run_id: runId, steering_state: 'injected' },
			created_at: at(4),
		})
		const secondAssistant = message({
			id: 'a2',
			type: 'assistant',
			parent_id: 'u2',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'iran news' }],
			created_at: at(5),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, toolResult, steeringUser, secondAssistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(2)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'assistant',
			'tool',
		])
		expect(result.blocks[0].responseRootId).toBe('a1')
		expect(result.blocks[0].agentId).toBe(agentId)
		expect(result.blocks[1].items.map((item) => item.kind)).toEqual(['user', 'assistant'])
		expect(result.blocks[1].responseRootId).toBe('a2')
		expect(result.blocks[1].agentId).toBe(agentId)
		expect(result.toolResults).toHaveLength(1)
		expect(result.toolResults[0].toolCallId).toBe('tc_search')
	})

	it('keeps tool-followup assistant messages in the same turn when no user intervenes', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [],
			tool_calls: [{ id: 'tc_search', name: 'agentic_web_search', arguments: {} }],
			created_at: at(2),
		})
		const toolResult = message({
			id: 't1',
			type: 'tool',
			parent_id: 'a1',
			sender_user_id: null,
			content: [{ type: 'text', text: 'search results' }],
			tool_call_id: 'tc_search',
			is_error: false,
			created_at: at(3),
		})
		const finalAssistant = message({
			id: 'a2',
			type: 'assistant',
			parent_id: 't1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'summary' }],
			created_at: at(4),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, toolResult, finalAssistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(1)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'tool',
			'assistant',
		])
		expect(result.blocks[0].agentId).toBe(agentId)
	})

	it('places run activity after its timeline anchor message', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const assistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'done' }],
			created_at: at(2),
		})
		const activity: RunActivityState = {
			key: 'activity_1',
			id: 'event_1',
			eventIds: ['event_1'],
			messageId: 'u1',
			runId,
			activityId: 'activity_1',
			activityType: 'context_compaction',
			status: 'success',
			updatedAt: new Date(at(1)),
			startedAt: new Date(at(1)),
			endedAt: new Date(at(1)),
		}

		const result = buildRunBlocks({
			messages: [firstUser, assistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
			runActivities: [activity],
		})

		expect(result.blocks).toHaveLength(1)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'run_activity',
			'assistant',
		])
		expect(result.blocks[0].agentId).toBe(agentId)
	})

	it('places late memory activity on its older anchor turn', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			metadata_: { run_id: 'run_1' },
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			metadata_: { run_id: 'run_1' },
			content: [{ type: 'text', text: 'first done' }],
			created_at: at(2),
		})
		const secondUser = message({
			id: 'u2',
			type: 'user',
			parent_id: 'a1',
			sender_user_id: userId,
			metadata_: { run_id: 'run_2' },
			created_at: at(3),
		})
		const secondAssistant = message({
			id: 'a2',
			type: 'assistant',
			parent_id: 'u2',
			sender_user_id: null,
			sender_agent_id: agentId,
			metadata_: { run_id: 'run_2' },
			content: [{ type: 'text', text: 'second done' }],
			created_at: at(4),
		})
		const activity: RunActivityState = {
			key: 'memory_activity_1',
			id: 'event_1',
			eventIds: ['event_1'],
			messageId: 'u1',
			runId: 'run_1',
			activityId: 'memory_activity_1',
			activityType: 'memory_maintenance',
			status: 'success',
			message: 'memory updated',
			updatedAt: new Date(at(5)),
			startedAt: new Date(at(5)),
			endedAt: new Date(at(5)),
		}

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, secondUser, secondAssistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
			runActivities: [activity],
		})

		expect(result.blocks).toHaveLength(2)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'run_activity',
			'assistant',
		])
		expect(result.blocks[1].items.map((item) => item.kind)).toEqual(['user', 'assistant'])
	})

	it('splits consecutive assistant and tool messages when the run id changes', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'first run' }],
			created_at: at(2),
		})
		const nextRunAssistant = message({
			id: 'a2',
			type: 'assistant',
			parent_id: 'a1',
			sender_user_id: null,
			sender_agent_id: agentId,
			metadata_: { run_id: 'run_2' },
			content: [{ type: 'text', text: 'second run' }],
			created_at: at(3),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, nextRunAssistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(2)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual(['user', 'assistant'])
		expect(result.blocks[1].items.map((item) => item.kind)).toEqual(['assistant'])
		expect(result.blocks[0].agentId).toBe(agentId)
		expect(result.blocks[1].agentId).toBe(agentId)
	})

	it('splits consecutive assistant and tool messages when the agent id changes', () => {
		const otherAgentId = 'agent_2'
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'checking' }],
			tool_calls: [{ id: 'tc_search', name: 'agentic_web_search', arguments: {} }],
			created_at: at(2),
		})
		const toolResult = message({
			id: 't1',
			type: 'tool',
			parent_id: 'a1',
			sender_user_id: null,
			content: [{ type: 'text', text: 'search results' }],
			tool_call_id: 'tc_search',
			is_error: false,
			created_at: at(3),
		})
		const otherAgentAssistant = message({
			id: 'a2',
			type: 'assistant',
			parent_id: 't1',
			sender_user_id: null,
			sender_agent_id: otherAgentId,
			content: [{ type: 'text', text: 'different agent' }],
			created_at: at(4),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, toolResult, otherAgentAssistant],
			userId,
			streamingAssistant: null,
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(2)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'assistant',
			'tool',
		])
		expect(result.blocks[1].items.map((item) => item.kind)).toEqual(['assistant'])
		expect(result.blocks[0].agentId).toBe(agentId)
		expect(result.blocks[1].agentId).toBe(otherAgentId)
	})

	it('places streaming assistant text before active streaming tools', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'checking' }],
			created_at: at(2),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant],
			userId,
			streamingAssistant: {
				runId,
				messageId: 'streaming_1',
				content: 'searching',
				timestamp: new Date(at(3)),
				senderAgentId: agentId,
				toolCalls: [{ id: 'tc_live', name: 'agentic_web_search', arguments: {} }],
				isError: false,
				errorMessage: null,
			},
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(1)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'assistant',
			'streaming_assistant',
			'streaming_tool',
		])
	})

	it('does not render an empty text placeholder before active streaming tools', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'checking' }],
			created_at: at(2),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant],
			userId,
			streamingAssistant: {
				runId,
				messageId: 'streaming_1',
				content: '',
				timestamp: new Date(at(3)),
				senderAgentId: agentId,
				toolCalls: [{ id: 'tc_live', name: 'agentic_web_search', arguments: {} }],
				isError: false,
				errorMessage: null,
			},
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(1)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'assistant',
			'streaming_tool',
		])
	})

	it('renders the text placeholder again after a streaming tool call resolves', () => {
		const firstUser = message({
			id: 'u1',
			type: 'user',
			parent_id: null,
			sender_user_id: userId,
			created_at: at(1),
		})
		const firstAssistant = message({
			id: 'a1',
			type: 'assistant',
			parent_id: 'u1',
			sender_user_id: null,
			sender_agent_id: agentId,
			content: [{ type: 'text', text: 'checking' }],
			created_at: at(2),
		})
		// tool result already arrived for tc_live
		const toolResult = message({
			id: 't1',
			type: 'tool',
			parent_id: 'a1',
			sender_user_id: null,
			content: [{ type: 'text', text: 'results' }],
			tool_call_id: 'tc_live',
			is_error: false,
			created_at: at(3),
		})

		const result = buildRunBlocks({
			messages: [firstUser, firstAssistant, toolResult],
			userId,
			streamingAssistant: {
				runId,
				messageId: 'streaming_1',
				content: '',
				timestamp: new Date(at(4)),
				senderAgentId: agentId,
				// the resolved tool call is still present on the streaming
				// message before the model emits its next text token
				toolCalls: [{ id: 'tc_live', name: 'agentic_web_search', arguments: {} }],
				isError: false,
				errorMessage: null,
			},
			optimisticUserMessage: null,
			viewingStreamingBranch: true,
		})

		expect(result.blocks).toHaveLength(1)
		expect(result.blocks[0].items.map((item) => item.kind)).toEqual([
			'user',
			'assistant',
			'streaming_assistant',
			'streaming_tool',
		])
	})
})
