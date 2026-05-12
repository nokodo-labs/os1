import { getAccessToken } from '$lib/auth/session.svelte'
import type { components } from '$lib/api/types'
import { getApiBaseUrl, refreshAccessToken } from '../client'
import { getSessionId } from '../sessionId'

type ApiTask = components['schemas']['Task']

export type TaskStreamDelta =
	| { event: 'task.created'; task: ApiTask }
	| { event: 'task.updated'; task: ApiTask }
	| { event: 'task.completed'; task: ApiTask }
	| { event: 'task.failed'; task: ApiTask }
	| { event: 'task.cancelled'; task: ApiTask }
	| { event: 'done'; task: null }

type RawSseFrame = {
	event: string
	data: string
}

async function openTaskStream(
	taskId: string,
	signal?: AbortSignal
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
	const url = `${getApiBaseUrl()}/v1/tasks/${encodeURIComponent(taskId)}/stream`
	const doRequest = async (token: string | null): Promise<Response> => {
		return fetch(url, {
			method: 'GET',
			credentials: 'include',
			headers: {
				Accept: 'text/event-stream',
				...(token ? { Authorization: `Bearer ${token}` } : {}),
				'X-Session-ID': getSessionId(),
			},
			signal,
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
		throw new Error(`task stream failed: ${response.status}`)
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
				let dataText = ''
				for (const line of rawEvent.split('\n')) {
					if (!line || line.startsWith(':')) continue
					if (line.startsWith('event:')) {
						eventType = line.slice(6).trim()
						continue
					}
					if (line.startsWith('data:')) {
						const chunk = line.slice(5).trim()
						dataText = dataText ? `${dataText}\n${chunk}` : chunk
					}
				}
				if (eventType) yield { event: eventType, data: dataText }
			}
		}
	} finally {
		reader.releaseLock()
	}
}

function parseTask(value: unknown): ApiTask | null {
	if (typeof value !== 'object' || value === null) return null
	const maybeTask = value as { id?: unknown }
	return typeof maybeTask.id === 'string' ? (value as ApiTask) : null
}

function parseTaskFrame(frame: RawSseFrame): TaskStreamDelta | null {
	if (frame.event === 'done') return { event: 'done', task: null }
	if (!frame.event.startsWith('task.')) return null
	const parsed = JSON.parse(frame.data) as { task?: unknown }
	const task = parseTask(parsed.task)
	if (task === null) return null
	if (
		frame.event === 'task.created' ||
		frame.event === 'task.updated' ||
		frame.event === 'task.completed' ||
		frame.event === 'task.failed' ||
		frame.event === 'task.cancelled'
	) {
		return { event: frame.event, task }
	}
	return null
}

export async function* streamTask(
	taskId: string,
	signal?: AbortSignal
): AsyncGenerator<TaskStreamDelta, void, unknown> {
	const reader = await openTaskStream(taskId, signal)
	for await (const frame of readSseFrames(reader)) {
		const delta = parseTaskFrame(frame)
		if (delta === null) continue
		yield delta
		if (delta.event === 'done') return
	}
}
