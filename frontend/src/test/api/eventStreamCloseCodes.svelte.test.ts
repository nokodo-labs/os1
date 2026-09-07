/**
 * close codes the client never reconnects from.
 *
 * 4001 (unauthorized) used to leave a silently dead socket: no reconnect, and
 * no logout either. it now takes the same hard-logout path as 4002.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

class FakeWebSocket {
	static readonly CONNECTING = 0
	static readonly OPEN = 1
	static readonly CLOSING = 2
	static readonly CLOSED = 3
	static instances: FakeWebSocket[] = []

	readyState = FakeWebSocket.OPEN
	onopen: (() => void) | null = null
	onmessage: ((event: { data: string }) => void) | null = null
	onclose: ((event: { code: number }) => void) | null = null
	onerror: (() => void) | null = null

	constructor(readonly url: string) {
		FakeWebSocket.instances.push(this)
	}

	send(): void {}

	close(): void {
		this.readyState = FakeWebSocket.CLOSED
	}
}

vi.mock('$lib/api/client', () => ({
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

vi.mock('$lib/api/sessionId', () => ({
	getSessionId: vi.fn(() => 'session_test'),
}))

const { EventStreamClient } = await import('$lib/api/streaming/eventStream.svelte')

/** the socket url is built in an async step, so let the microtasks drain. */
async function flushMicrotasks(): Promise<void> {
	for (let i = 0; i < 5; i++) await Promise.resolve()
}

/** connect and hand back the socket the client just opened. */
async function connectClient(
	client: InstanceType<typeof EventStreamClient>
): Promise<FakeWebSocket> {
	const opened = FakeWebSocket.instances.length
	client.connect()
	await flushMicrotasks()
	const socket = FakeWebSocket.instances[opened]
	socket.onopen?.()
	return socket
}

describe('websocket close codes', () => {
	beforeEach(() => {
		FakeWebSocket.instances = []
		vi.stubGlobal('WebSocket', FakeWebSocket)
		vi.useFakeTimers()
	})

	afterEach(() => {
		vi.useRealTimers()
		vi.unstubAllGlobals()
	})

	it('hands 4001 to the session-revoked handlers and stays down', async () => {
		const client = new EventStreamClient()
		const revoked = vi.fn()
		client.onSessionRevoked(revoked)
		const socket = await connectClient(client)

		socket.onclose?.({ code: 4001 })

		expect(revoked).toHaveBeenCalledTimes(1)
		expect(client.state.status).toBe('disconnected')

		// no reconnect is scheduled: the credential, not the socket, is the problem
		vi.advanceTimersByTime(60_000)
		await flushMicrotasks()
		expect(FakeWebSocket.instances).toHaveLength(1)

		client.disconnect()
	})

	it('still hands 4002 over and still leaves 4003 alone', async () => {
		const revokedClient = new EventStreamClient()
		const revoked = vi.fn()
		revokedClient.onSessionRevoked(revoked)
		const revokedSocket = await connectClient(revokedClient)
		revokedSocket.onclose?.({ code: 4002 })
		expect(revoked).toHaveBeenCalledTimes(1)
		revokedClient.disconnect()

		const originClient = new EventStreamClient()
		const notRevoked = vi.fn()
		originClient.onSessionRevoked(notRevoked)
		const originSocket = await connectClient(originClient)
		originSocket.onclose?.({ code: 4003 })
		expect(notRevoked).not.toHaveBeenCalled()
		originClient.disconnect()
	})
})
