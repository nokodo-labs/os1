import {
	ToolExecutionTracker,
	getToolSummary,
	type ToolEvent,
	type ToolExecution,
} from '$lib/tools'
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
})
