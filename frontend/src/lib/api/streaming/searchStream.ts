/**
 * SSE client for the unified search endpoint.
 * GET /v1/search/stream?q=...&types=...&limit=...
 *
 * streams `result` events as they arrive, ends with `done`.
 */

import { getAccessToken } from '$lib/auth/session.svelte'
import { getApiBaseUrl, refreshAccessToken } from '../client'
import { getSessionId } from '../sessionId'

export type SearchResultType =
	| 'thread'
	| 'reminder'
	| 'calendar_event'
	| 'note'
	| 'memory'
	| 'project'
	| 'file'

export type SearchResourceType = Exclude<SearchResultType, 'memory'>

export const SEARCH_RESOURCE_TYPES: SearchResourceType[] = [
	'thread',
	'note',
	'reminder',
	'calendar_event',
	'project',
	'file',
]

export interface SearchResult {
	type: SearchResultType
	id: string
	title: string
	preview?: string | null
	metadata?: Record<string, unknown>
	created_at: string
	updated_at: string
}

export interface SearchStreamOptions {
	query: string
	types?: SearchResultType[]
	limit?: number
	mode?: 'hybrid' | 'dense' | 'sparse' | 'autocomplete' | 'full'
	signal?: AbortSignal
}

/**
 * stream search results from the SSE search endpoint.
 * yields SearchResult objects as they arrive.
 */
export async function* searchStream(
	opts: SearchStreamOptions
): AsyncGenerator<SearchResult, void, unknown> {
	const params = new URLSearchParams({ q: opts.query })
	if (opts.types?.length) {
		for (const t of opts.types) params.append('types', t)
	}
	if (opts.limit) params.set('limit', String(opts.limit))
	if (opts.mode) params.set('mode', opts.mode)

	const url = `${getApiBaseUrl()}/v1/search/stream?${params}`

	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(url, {
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
		return
	}

	const reader = response.body.getReader()
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

				if (eventType === 'done') return
				if (eventType === 'result' && dataStr) {
					try {
						yield JSON.parse(dataStr) as SearchResult
					} catch {
						// skip malformed results
					}
				}
			}
		}
	} finally {
		reader.releaseLock()
	}
}
