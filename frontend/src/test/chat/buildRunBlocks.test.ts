import { buildRunBlocks } from '$lib/chat/helpers'
import type { ApiMessage } from '$lib/chat/types'
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
})
