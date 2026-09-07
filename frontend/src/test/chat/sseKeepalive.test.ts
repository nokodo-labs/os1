/**
 * the run stream is kept warm with SSE comment frames (`: ping`) while the
 * agent is quiet. they carry no event, so nothing downstream may see them: a
 * ping must not close a tool call, finish the text, or reach the unknown-event
 * path that rebuilds the bubble and toasts.
 */

import { describe, expect, it, vi } from 'vitest'

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/device.svelte', () => ({
	getClientContext: vi.fn(() => null),
}))

vi.mock('$lib/stores/preferences.svelte', () => ({
	preferences: { data: { privacy: { useDeviceContext: false, useBatteryStatus: false } } },
}))

vi.mock('$lib/api/client', () => ({
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
	refreshAccessToken: vi.fn(async () => null),
}))

vi.mock('$lib/api/sessionId', () => ({
	getSessionId: vi.fn(() => 'session_test'),
}))

import { runChatStream, type ChatStreamDelta } from '$lib/api/streaming/chatStream'

/** serve a fixed byte script as the SSE response body, split at the given cuts. */
function serve(chunks: string[]): void {
	const encoder = new TextEncoder()
	const body = new ReadableStream<Uint8Array>({
		start(controller) {
			for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
			controller.close()
		},
	})
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => new Response(body, { status: 200 }))
	)
}

async function collect(): Promise<ChatStreamDelta[]> {
	const deltas: ChatStreamDelta[] = []
	for await (const delta of runChatStream({ agentId: 'agent_1', input: null })) {
		deltas.push(delta)
	}
	return deltas
}

const textDelta = (text: string): string =>
	`event: delta\ndata: ${JSON.stringify({
		run_id: 'run_1',
		agent_id: 'agent_1',
		message_id: 'msg_1',
		splice: null,
		delta: { chat: { message: { content: [{ type: 'text', text }] }, done: false } },
	})}\n\n`

describe('sse keepalive frames', () => {
	it('drops pings between events instead of yielding anything for them', async () => {
		serve([
			': ping\n\n',
			textDelta('one'),
			': ping\n\n',
			textDelta('two'),
			'event: done\ndata: {}\n\n',
		])

		const deltas = await collect()

		expect(deltas.map((d) => d.event)).toEqual(['delta', 'delta', 'done'])
	})

	it('never reports a ping as an unknown event', async () => {
		serve([': keep-alive comment\n\n', 'event: done\ndata: {}\n\n'])

		const deltas = await collect()

		// the unknown path warns, toasts, and is the only way a stray frame can
		// reach the run bubble at all.
		expect(deltas.some((d) => d.event === 'unknown')).toBe(false)
	})

	it('reads a real event that arrives split around a ping', async () => {
		// the transport can cut anywhere, so a frame boundary is not a chunk
		// boundary - the parser has to buffer rather than parse per chunk.
		serve([
			'event: delta\ndata: {"run_id":"run_1","agent_id":"agent_1","message_id":"msg_1","splice":null,',
			'"delta":{"chat":{"message":{"content":[{"type":"text","text":"split"}]},"done":false}}}\n\n',
			': ping\n\n',
			'event: done\ndata: {}\n\n',
		])

		const deltas = await collect()

		expect(deltas.map((d) => d.event)).toEqual(['delta', 'done'])
	})
})
