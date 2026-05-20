import {
	ToolExecutionTracker,
	getToolSummary,
	type ToolEvent,
	type ToolExecution,
} from '$lib/tools'
import {
	getWebSearchProgressItems,
	getWebSearchQueries,
	getWebSearchSources,
} from '$lib/tools/webSearch'
import { describe, expect, it } from 'vitest'

function progressEvent(toolCallId: string): ToolEvent {
	return {
		id: `event_${toolCallId}`,
		type: 'tool.progress',
		toolCallId,
		toolName: 'agentic_web_search',
		timestamp: new Date(),
		data: { progress: 0.5, message: 'searching' },
	}
}

function completedTool(
	name: string,
	args: Record<string, unknown>,
	output: Record<string, unknown>
): ToolExecution {
	return {
		toolCall: { id: `tc_${name}`, name, arguments: args },
		status: 'completed',
		events: [],
		result: {
			toolCallId: `tc_${name}`,
			output: JSON.stringify(output),
			isError: false,
		},
	}
}

describe('ToolExecutionTracker', () => {
	it('does not move a completed tool back to running when late events arrive', () => {
		const tracker = new ToolExecutionTracker()
		tracker.registerToolCall({
			id: 'tc_search',
			name: 'agentic_web_search',
			arguments: { query: 'news' },
		})
		tracker.processEvent(progressEvent('tc_search'))
		expect(tracker.get('tc_search')?.status).toBe('running')

		tracker.registerResult({
			toolCallId: 'tc_search',
			output: 'done',
			isError: false,
		})
		expect(tracker.get('tc_search')?.status).toBe('completed')

		tracker.processEvent(progressEvent('tc_search'))
		expect(tracker.get('tc_search')?.status).toBe('completed')
	})

	it('keeps result-before-call executions completed after later call and event data', () => {
		const tracker = new ToolExecutionTracker()
		tracker.registerResult({
			toolCallId: 'tc_search',
			output: 'done',
			isError: false,
		})
		expect(tracker.get('tc_search')?.status).toBe('completed')

		tracker.registerToolCall({
			id: 'tc_search',
			name: 'agentic_web_search',
			arguments: { query: 'news' },
		})
		tracker.processEvent(progressEvent('tc_search'))

		const execution = tracker.get('tc_search')
		expect(execution?.status).toBe('completed')
		expect(execution?.toolCall.name).toBe('agentic_web_search')
		expect(execution?.toolCall.arguments).toEqual({ query: 'news' })
	})

	it('uses think summaries as the visible title', () => {
		const completed: ToolExecution = {
			toolCall: {
				id: 'tc_think_done',
				name: 'think',
				arguments: {
					thoughts: [{ text: 'inspect the queue ordering', summary: 'queue ordering' }],
				},
			},
			status: 'completed',
			events: [],
			result: {
				toolCallId: 'tc_think_done',
				output: '{"elapsed_seconds":1.2}',
				isError: false,
			},
		}
		const streaming: ToolExecution = {
			toolCall: { id: 'tc_think_stream', name: 'think', arguments: {} },
			status: 'running',
			events: [],
			rawArguments: '{"thoughts":[{"text":"inspect","summary":"streamed title',
		}

		expect(getToolSummary(completed).title).toBe('queue ordering')
		expect(getToolSummary(streaming).title).toBe('streamed title')
	})

	it('parses rich agentic web search progress events', () => {
		const execution: ToolExecution = {
			toolCall: {
				id: 'tc_search',
				name: 'agentic_web_search',
				arguments: { query: 'latest news' },
			},
			status: 'completed',
			events: [
				{
					id: 'ev_search',
					type: 'tool.progress',
					toolCallId: 'tc_search',
					toolName: 'agentic_web_search',
					timestamp: new Date(),
					data: {
						message: 'found 1 resources',
						payload: {
							web_search: {
								kind: 'agentic_web_search',
								stage: 'completed',
								message: 'found 1 resources',
								agent: { name: 'native' },
								engine: { name: 'perplexity' },
								query: { text: 'latest news' },
								searches: [
									{
										id: 'inner_1',
										query: { text: 'latest news' },
										status: 'completed',
										result_count: 1,
									},
								],
								resources: {
									count: 1,
									sources: [
										{
											title: 'example source',
											url: 'https://example.com/source',
											snippet: 'snippet',
										},
									],
								},
							},
						},
					},
				},
			],
		}

		expect(getWebSearchQueries(execution)).toEqual(['latest news'])
		expect(getWebSearchSources(execution)).toEqual([
			{
				url: 'https://example.com/source',
				title: 'example source',
				snippet: 'snippet',
				domain: 'example.com',
			},
		])
		expect(getWebSearchProgressItems(execution)).toEqual([
			{
				id: 'ev_search',
				stage: 'completed',
				message: 'found 1 resources',
				query: 'latest news',
				resultCount: 1,
				sourceCount: 1,
				agent: 'native',
				engine: 'perplexity',
			},
		])
		expect(getToolSummary(execution).title).toBe('searched 1 sources')
	})

	it('parses web search sources from explicit JSON output', () => {
		const execution: ToolExecution = {
			toolCall: {
				id: 'tc_web_search',
				name: 'web_search',
				arguments: { query: 'source query' },
			},
			status: 'completed',
			events: [],
			result: {
				toolCallId: 'tc_web_search',
				isError: false,
				output: JSON.stringify({
					results: [
						{
							title: 'json source',
							url: 'https://example.com/json-source',
							snippet: 'from output',
						},
					],
				}),
			},
		}

		expect(getWebSearchSources(execution)).toEqual([
			{
				url: 'https://example.com/json-source',
				title: 'json source',
				snippet: 'from output',
				domain: 'example.com',
			},
		])
	})

	it('ignores web search source metadata', () => {
		const execution: ToolExecution = {
			toolCall: {
				id: 'tc_web_search',
				name: 'web_search',
				arguments: { query: 'source query' },
			},
			status: 'completed',
			events: [],
			result: {
				toolCallId: 'tc_web_search',
				isError: false,
				output: '',
				metadata: {
					_web_search: { engine: 'perplexity' },
					_citable_sources: [
						{ title: 'citation source', source_id: 'https://example.com/cite' },
					],
				},
			},
		}

		expect(getWebSearchSources(execution)).toEqual([])
	})

	it('summarizes reminder search results from split list and reminder counts', () => {
		const execution = completedTool(
			'reminder_get',
			{ query: 'draft' },
			{ list_count: 1, reminder_count: 2, reminder_lists: [], reminders: [] }
		)

		expect(getToolSummary(execution)).toEqual({
			title: 'found 3 reminder results',
			subtitle: 'draft',
		})
	})

	it('summarizes direct reminder and list payloads from nested fields', () => {
		const reminderExecution = completedTool(
			'reminder_get',
			{ reminder_id: 'rem_1' },
			{ reminder: { id: 'rem_1', title: 'send draft', list_id: 'list_1' } }
		)
		const listExecution = completedTool(
			'reminder_get',
			{ list_id: 'list_1' },
			{ list: { id: 'list_1', name: 'work', total_count: 3 } }
		)

		expect(getToolSummary(reminderExecution)).toEqual({
			title: 'checked send draft',
			resourceId: 'rem_1',
			resourceType: 'reminder',
		})
		expect(getToolSummary(listExecution)).toEqual({
			title: 'checked work',
			resourceId: 'list_1',
			resourceType: 'reminder_list',
		})
	})

	it('summarizes calendar scheduled items and direct events', () => {
		const upcomingExecution = completedTool('calendar_event_get', {}, { count: 2, results: [] })
		const eventExecution = completedTool(
			'calendar_event_get',
			{ calendar_event_id: 'calev_1' },
			{ event: { id: 'calev_1', title: 'planning sync' } }
		)

		expect(getToolSummary(upcomingExecution)).toEqual({ title: 'found 2 scheduled items' })
		expect(getToolSummary(eventExecution)).toEqual({
			title: 'read planning sync',
			resourceId: 'calev_1',
			resourceType: 'calendar_event',
		})
	})

	it('summarizes chat and global resource search outputs', () => {
		const chatExecution = completedTool(
			'chat_get',
			{ chat_id: 'thread_1' },
			{ chat: { chat_id: 'thread_1', title: 'release notes' }, message_page: {} }
		)
		const resourceSearchExecution = completedTool(
			'resource_search',
			{ query: 'release' },
			{ count: 4 }
		)

		expect(getToolSummary(chatExecution)).toEqual({
			title: 'read release notes',
			resourceId: 'thread_1',
			resourceType: 'chat',
		})
		expect(getToolSummary(resourceSearchExecution)).toEqual({
			title: 'found 4 resources',
			subtitle: 'release',
		})
	})
})
