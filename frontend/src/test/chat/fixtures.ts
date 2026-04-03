/**
 * shared test fixtures and factory helpers for chat module tests.
 * provides builders for Thread, ApiMessage, StreamMessage, and other common types.
 */

import type { components } from '$lib/api/types'
import type { ApiCitation, ApiMessage, StreamingAssistantState } from '$lib/chat/types'

export type Thread = components['schemas']['Thread']

let idCounter = 0

/** generate a unique ID with an optional prefix */
export function uniqueId(prefix = 'id'): string {
	return `${prefix}_${++idCounter}`
}

/** reset the ID counter between tests */
export function resetIdCounter(): void {
	idCounter = 0
}

/** create a minimal valid Thread object with overrides */
export function makeThread(overrides: Partial<Thread> = {}): Thread {
	const id = overrides.id ?? uniqueId('thread')
	return {
		id,
		title: 'test thread',
		tags: [],
		is_archived: false,
		is_temporary: false,
		owner_id: uniqueId('user'),
		current_message_id: null,
		last_activity_at: new Date().toISOString(),
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
		deleted_at: null,
		projects: [],
		...overrides,
	}
}

/** create a minimal stream message (as received from eventStreamClient) */
export function makeStreamMessage(
	type: string,
	data: Record<string, unknown> = {},
	extra: Record<string, unknown> = {}
): { type: string; data: Record<string, unknown>; [k: string]: unknown } {
	return { type, data, ...extra }
}

/** create a minimal ApiMessage */
export function makeApiMessage(overrides: Partial<ApiMessage> = {}): ApiMessage {
	const id = overrides.id ?? uniqueId('msg')
	return {
		id,
		thread_id: uniqueId('thread'),
		parent_id: null,
		type: 'user',
		content: [{ type: 'text', text: 'hello' }],
		tool_calls: [],
		sender_agent_id: null,
		sender_user_id: uniqueId('user'),
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
		...overrides,
	} as ApiMessage
}

/** create a minimal assistant message */
export function makeAssistantMessage(
	id: string,
	content: string,
	threadId = 'thread_1'
): ApiMessage {
	return {
		id,
		thread_id: threadId,
		parent_id: null,
		type: 'assistant',
		content: [{ type: 'text', text: content }],
		tool_calls: [],
		sender_agent_id: uniqueId('agent'),
		sender_user_id: null,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	} as ApiMessage
}

/** create a citation fixture */
export function makeCitation(index: number, sourceType = 'url'): ApiCitation {
	return {
		index,
		source_type: sourceType as ApiCitation['source_type'],
		source_id: `https://example.com/${index}`,
		title: `source ${index}`,
	}
}

/** create a streaming assistant state fixture */
export function makeStreamingState(messageId: string, content = ''): StreamingAssistantState {
	return {
		runId: uniqueId('run'),
		messageId,
		content,
		timestamp: new Date(),
		senderAgentId: uniqueId('agent'),
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
}
