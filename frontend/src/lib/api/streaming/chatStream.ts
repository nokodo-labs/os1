/**
 * SSE client for chat run streaming.
 * POST /runs - run on an existing thread (or ephemeral, not yet implemented).
 * POST /threads/create_and_run - create a new thread and run immediately.
 * GET  /runs/{runId}/stream - resume an active run.
 *
 * these types mirror backend schemas and SSE event payloads.
 */

import { getAccessToken } from '$lib/auth/session.svelte'
import { getClientContext } from '$lib/stores/device.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { getApiBaseUrl, refreshAccessToken } from '../client'
import { getSessionId } from '../sessionId'

export interface RawSseFrame {
	event: string
	data: string
}

// types

/** content part in a message. */
export interface ContentPart {
	type: 'text' | 'image' | string
	text?: string
	url?: string
	[key: string]: unknown
}

/** message structure returned by message_created event. */
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
	parent_id: string | null
	delta: unknown
}

/** unknown event received from the server (future-proofing). */
export interface UnknownSseEvent {
	eventType: string
	rawData: string
}

/** discriminated union for all SSE events from the chat stream. */
export type ChatStreamDelta =
	| { event: 'delta'; data: AgentDeltaEnvelope }
	| { event: 'message_created'; data: StreamedMessage }
	| { event: 'text_delta'; data: TextDelta }
	| { event: 'tool_result'; data: ToolResultDelta }
	| { event: 'done'; data: null }
	| { event: 'error'; data: StreamError }
	| { event: 'unknown'; data: UnknownSseEvent }

// known event types for run streams
const KNOWN_RUN_EVENTS = new Set([
	'error',
	'done',
	'message_created',
	'delta',
	'text_delta',
	'tool_result',
])

// known event types for create_and_run streams (includes thread_created)
const KNOWN_CREATE_AND_RUN_EVENTS = new Set([...KNOWN_RUN_EVENTS, 'thread_created'])

// shared frame parsing

/**
 * parses a raw SSE frame into a typed ChatStreamDelta.
 * returns null for terminal events (done/error) that should end the stream.
 * throws for error events to signal caller.
 */
function parseRunFrame(
	frame: RawSseFrame,
	knownEvents: Set<string>
): { delta: ChatStreamDelta; terminal: boolean } {
	const { event: eventType, data: dataStr } = frame

	// unknown event - yield but continue
	if (!knownEvents.has(eventType)) {
		return {
			delta: { event: 'unknown', data: { eventType, rawData: dataStr } },
			terminal: false,
		}
	}

	switch (eventType) {
		case 'error': {
			const parsed = JSON.parse(dataStr) as StreamError
			return { delta: { event: 'error', data: parsed }, terminal: true }
		}
		case 'done':
			return { delta: { event: 'done', data: null }, terminal: true }
		case 'message_created': {
			const parsed = JSON.parse(dataStr) as StreamedMessage
			return { delta: { event: 'message_created', data: parsed }, terminal: false }
		}
		case 'delta': {
			const parsed = JSON.parse(dataStr) as AgentDeltaEnvelope
			return { delta: { event: 'delta', data: parsed }, terminal: false }
		}
		case 'text_delta': {
			const parsed = JSON.parse(dataStr) as TextDelta
			return { delta: { event: 'text_delta', data: parsed }, terminal: false }
		}
		case 'tool_result': {
			const parsed = JSON.parse(dataStr) as ToolResultDelta
			return { delta: { event: 'tool_result', data: parsed }, terminal: false }
		}
		default:
			// should not reach here if knownEvents is maintained correctly
			return {
				delta: { event: 'unknown', data: { eventType, rawData: dataStr } },
				terminal: false,
			}
	}
}

// shared streaming transport

async function streamSseFrames(opts: {
	url: string
	body: Record<string, unknown>
	signal?: AbortSignal
}): Promise<ReadableStreamDefaultReader<Uint8Array>> {
	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(opts.url, {
			method: 'POST',
			credentials: 'include',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
				'X-Session-ID': getSessionId(),
			},
			body: JSON.stringify(opts.body),
			signal: opts.signal,
		})
	}

	let token = getAccessToken()
	let response = await doRequest(token)

	if (response.status === 401) {
		const refreshed = await refreshAccessToken()
		if (refreshed) {
			token = refreshed
			response = await doRequest(token)
		}
	}

	if (!response.ok || !response.body) {
		throw new Error(`stream request failed: ${response.status}`)
	}

	return response.body.getReader()
}

async function streamSseGet(opts: {
	url: string
	signal?: AbortSignal
}): Promise<ReadableStreamDefaultReader<Uint8Array>> {
	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(opts.url, {
			method: 'GET',
			credentials: 'include',
			headers: {
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
				'X-Session-ID': getSessionId(),
			},
			signal: opts.signal,
		})
	}

	let token = getAccessToken()
	let response = await doRequest(token)

	if (response.status === 401) {
		const refreshed = await refreshAccessToken()
		if (refreshed) {
			token = refreshed
			response = await doRequest(token)
		}
	}

	if (!response.ok || !response.body) {
		throw new Error(`resume stream failed: ${response.status}`)
	}

	return response.body.getReader()
}

async function* readSseFrames(
	reader: ReadableStreamDefaultReader<Uint8Array>
): AsyncGenerator<RawSseFrame, void, unknown> {
	const decoder = new TextDecoder()
	let buffer = ''

	try {
		while (true) {
			const { value, done } = await reader.read()
			if (done) break

			buffer += decoder.decode(value, { stream: true })
			buffer = buffer.replace(/\r\n/g, '\n')

			let splitIndex = buffer.indexOf('\n\n')
			while (splitIndex !== -1) {
				const rawEvent = buffer.slice(0, splitIndex)
				buffer = buffer.slice(splitIndex + 2)
				splitIndex = buffer.indexOf('\n\n')

				let eventType = ''
				let dataStr = ''
				for (const line of rawEvent.split('\n')) {
					if (!line) continue
					if (line.startsWith(':')) continue
					if (line.startsWith('event:')) {
						eventType = line.slice(6).trim()
						continue
					}
					if (line.startsWith('data:')) {
						const chunk = line.slice(5).trim()
						dataStr = dataStr ? `${dataStr}\n${chunk}` : chunk
					}
				}
				if (!eventType) continue

				yield { event: eventType, data: dataStr }
			}
		}
	} finally {
		reader.releaseLock()
	}
}

// run chat stream

export interface ChatStreamOptions {
	threadId?: string | null
	agentId: string
	input: string | null
	parentId?: string | null
	persist?: boolean
	signal?: AbortSignal
}

/**
 * async generator that yields typed SSE events from a chat run stream.
 * posts to /v1/runs with a thread_id to continue an existing thread.
 * handles 401 refresh transparently via sseUtils.
 */
export async function* runChatStream(
	opts: ChatStreamOptions
): AsyncGenerator<ChatStreamDelta, void, unknown> {
	const url = `${getApiBaseUrl()}/v1/runs`
	const clientContext = preferences.data.privacy.useDeviceContext ? getClientContext() : null
	if (clientContext && !preferences.data.privacy.useBatteryStatus) {
		clientContext.batterySupported = false
		clientContext.batteryCharging = null
		clientContext.batteryLevel = null
		clientContext.batteryChargingTimeSeconds = null
		clientContext.batteryDischargingTimeSeconds = null
	}

	const body: Record<string, unknown> = {
		agent_id: opts.agentId,
		input: opts.input,
		parent_id: opts.parentId,
		stream: true,
	}
	if (opts.threadId) body.thread_id = opts.threadId
	if (opts.persist === false) body.persist = false
	if (clientContext) body.clientContext = clientContext

	const reader = await streamSseFrames({ url, body, signal: opts.signal })
	for await (const frame of readSseFrames(reader)) {
		const { delta, terminal } = parseRunFrame(frame, KNOWN_RUN_EVENTS)
		yield delta
		if (terminal) return
	}
}

// create_and_run stream (thread creation + run in one request)

/** thread data emitted as the first SSE event by create_and_run. */
export interface CreateAndRunThread {
	id: string
	title?: string | null
	is_temporary: boolean
	[key: string]: unknown
}

/** discriminated union for create_and_run SSE events. */
export type CreateAndRunStreamDelta =
	| { event: 'thread_created'; data: CreateAndRunThread }
	| ChatStreamDelta

export interface CreateAndRunStreamOptions {
	agentId: string
	input: string
	isTemporary?: boolean
	tags?: string[]
	projectIds?: string[]
	signal?: AbortSignal
}

/**
 * async generator that yields typed SSE events from a create_and_run stream.
 * posts to /v1/threads/create_and_run - the backend creates a thread
 * and emits a ``thread_created`` event first, followed by normal run events.
 */
export async function* runCreateAndRunStream(
	opts: CreateAndRunStreamOptions
): AsyncGenerator<CreateAndRunStreamDelta, void, unknown> {
	const url = `${getApiBaseUrl()}/v1/threads/create_and_run`
	const clientContext = preferences.data.privacy.useDeviceContext ? getClientContext() : null
	if (clientContext && !preferences.data.privacy.useBatteryStatus) {
		clientContext.batterySupported = false
		clientContext.batteryCharging = null
		clientContext.batteryLevel = null
		clientContext.batteryChargingTimeSeconds = null
		clientContext.batteryDischargingTimeSeconds = null
	}

	const body: Record<string, unknown> = {
		agent_id: opts.agentId,
		input: opts.input,
		is_temporary: opts.isTemporary ?? false,
		tags: opts.tags ?? [],
		project_ids: opts.projectIds ?? [],
		stream: true,
	}
	if (clientContext) body.clientContext = clientContext

	const reader = await streamSseFrames({ url, body, signal: opts.signal })
	for await (const frame of readSseFrames(reader)) {
		// handle thread_created specially (not in parseRunFrame)
		if (frame.event === 'thread_created') {
			const parsed = JSON.parse(frame.data) as CreateAndRunThread
			yield { event: 'thread_created', data: parsed }
			continue
		}

		const { delta, terminal } = parseRunFrame(frame, KNOWN_CREATE_AND_RUN_EVENTS)
		yield delta
		if (terminal) return
	}
}

// resume run stream (GET-based SSE for re-joining an active run)

export interface ResumeRunStreamOptions {
	runId: string
	signal?: AbortSignal
}

/**
 * async generator that yields typed SSE events from a resumed run stream.
 * connects to GET /runs/{runId}/stream which replays catchup frames
 * followed by live deltas until the run completes.
 */
export async function* resumeRunStream(
	opts: ResumeRunStreamOptions
): AsyncGenerator<ChatStreamDelta, void, unknown> {
	const url = `${getApiBaseUrl()}/v1/runs/${opts.runId}/stream`
	const reader = await streamSseGet({ url, signal: opts.signal })
	for await (const frame of readSseFrames(reader)) {
		const { delta, terminal } = parseRunFrame(frame, KNOWN_RUN_EVENTS)
		yield delta
		if (terminal) return
	}
}
