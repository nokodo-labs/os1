/**
 * SSE client for chat run streaming.
 * POST /threads/{thread_id}/run
 *
 * These types mirror backend schemas and SSE event payloads.
 */

import { getAccessToken } from '$lib/auth/session'
import { getV1BaseUrl, refreshV1AccessToken } from '../v1/client'

/** Content part in a message. */
export interface ContentPart {
	type: 'text' | 'image' | string
	text?: string
	url?: string
	[key: string]: unknown
}

/** Message structure returned by message_created event. */
export interface StreamedMessage {
	id: string
	thread_id: string
	parent_id?: string | null
	type: 'user' | 'assistant' | 'tool' | 'system' | string
	content: ContentPart[]
	metadata_?: Record<string, unknown>
	sender_agent_id?: string | null
	sender_user_id?: string | null
	created_at?: string | null
}

/** text_delta event payload. */
export interface TextDelta {
	text: string
}

/** error event payload. */
export interface StreamError {
	message: string
}

/** tool_result event payload. */
export interface ToolResultDelta {
	tool_call_id: string
	is_error: boolean
	completed: boolean
}

/** delta event envelope (faithfully forwards backend AgentDelta). */
export interface AgentDeltaEnvelope {
	run_id: string
	message_id: string | null
	delta: unknown
}

/** Discriminated union for all SSE events from the chat stream. */
export type ChatStreamDelta =
	| { event: 'delta'; data: AgentDeltaEnvelope }
	| { event: 'message_created'; data: StreamedMessage }
	| { event: 'text_delta'; data: TextDelta }
	| { event: 'tool_result'; data: ToolResultDelta }
	| { event: 'done'; data: null }
	| { event: 'error'; data: StreamError }

export interface ChatStreamOptions {
	threadId: string
	agentId: string
	input: string | null
	parentId?: string | null
	signal?: AbortSignal
}

/**
 * Async generator that yields typed SSE events from a chat run stream.
 * Handles 401 refresh transparently.
 */
export async function* runChatStream(
	opts: ChatStreamOptions
): AsyncGenerator<ChatStreamDelta, void, unknown> {
	const streamUrl = `${getV1BaseUrl()}/threads/${opts.threadId}/run`

	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(streamUrl, {
			method: 'POST',
			credentials: 'include',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
			},
			body: JSON.stringify({
				agent_id: opts.agentId,
				input: opts.input,
				parent_id: opts.parentId,
			}),
			signal: opts.signal,
		})
	}

	let token = getAccessToken()
	let response = await doRequest(token)

	if (response.status === 401) {
		const refreshed = await refreshV1AccessToken()
		if (refreshed) {
			token = refreshed
			response = await doRequest(token)
		}
	}

	if (!response.ok || !response.body) {
		throw new Error(`stream request failed: ${response.status}`)
	}

	const reader = response.body.getReader()
	const decoder = new TextDecoder()
	let buffer = ''

	try {
		while (true) {
			const { value, done } = await reader.read()
			if (done) break

			buffer += decoder.decode(value, { stream: true })

			let splitIndex = buffer.indexOf('\n\n')
			while (splitIndex !== -1) {
				const rawEvent = buffer.slice(0, splitIndex)
				buffer = buffer.slice(splitIndex + 2)
				splitIndex = buffer.indexOf('\n\n')

				let eventType = ''
				let dataStr = ''
				for (const line of rawEvent.split('\n')) {
					if (line.startsWith('event:')) eventType = line.slice(6).trim()
					if (line.startsWith('data:')) dataStr += line.slice(5).trim()
				}
				if (!eventType) continue

				if (eventType === 'error') {
					const parsed = JSON.parse(dataStr) as StreamError
					yield { event: 'error', data: parsed }
					return
				}

				if (eventType === 'done') {
					yield { event: 'done', data: null }
					return
				}

				if (eventType === 'message_created') {
					const parsed = JSON.parse(dataStr) as StreamedMessage
					yield { event: 'message_created', data: parsed }
					continue
				}

				if (eventType === 'delta') {
					const parsed = JSON.parse(dataStr) as AgentDeltaEnvelope
					yield { event: 'delta', data: parsed }
					continue
				}

				if (eventType === 'text_delta') {
					const parsed = JSON.parse(dataStr) as TextDelta
					yield { event: 'text_delta', data: parsed }
					continue
				}

				if (eventType === 'tool_result') {
					const parsed = JSON.parse(dataStr) as ToolResultDelta
					yield { event: 'tool_result', data: parsed }
					continue
				}
			}
		}
	} finally {
		reader.releaseLock()
	}
}
