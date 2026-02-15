/**
 * shared SSE utilities for streaming endpoints.
 * centralizes fetch + 401 refresh + SSE parsing logic.
 */

import { getAccessToken } from '$lib/auth/session.svelte'
import { refreshAccessToken } from '../client'

/** raw parsed SSE frame from the stream. */
export interface RawSseFrame {
	event: string
	data: string
}

export interface SseRequestOptions {
	/** full URL to POST to. */
	url: string
	/** JSON body to send. */
	body: Record<string, unknown>
	/** abort signal for the request. */
	signal?: AbortSignal
}

/**
 * makes a POST request with SSE response handling, including 401 token refresh.
 * returns the Response object for the caller to consume the body.
 */
export async function sseRequest(opts: SseRequestOptions): Promise<Response> {
	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(opts.url, {
			method: 'POST',
			credentials: 'include',
			headers: {
				'Content-Type': 'application/json',
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
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

	return response
}

/**
 * async generator that yields raw SSE frames from a ReadableStream.
 * handles buffering, newline parsing, and frame extraction.
 */
export async function* parseSseStream(
	body: ReadableStream<Uint8Array>
): AsyncGenerator<RawSseFrame, void, unknown> {
	const reader = body.getReader()
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

				yield { event: eventType, data: dataStr }
			}
		}
	} finally {
		reader.releaseLock()
	}
}

/**
 * convenience helper: makes request + streams SSE frames.
 */
export async function* streamSse(
	opts: SseRequestOptions
): AsyncGenerator<RawSseFrame, void, unknown> {
	const response = await sseRequest(opts)
	yield* parseSseStream(response.body!)
}
