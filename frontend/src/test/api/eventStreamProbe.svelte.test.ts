/**
 * probe(): the only way a zombie socket becomes a visible drop.
 *
 * on mobile the OS kills the socket while the app is backgrounded and never
 * delivers a close event, so `readyState` keeps reading OPEN. resume signals
 * probe instead of guessing: a live socket pongs and nothing happens, a dead
 * one runs out the pong deadline and reconnects, which is what marks the gap.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

class FakeWebSocket {
	static readonly CONNECTING = 0
	static readonly OPEN = 1
	static readonly CLOSING = 2
	static readonly CLOSED = 3
	static instances: FakeWebSocket[] = []

	readyState = FakeWebSocket.OPEN
	sent: string[] = []
	onopen: (() => void) | null = null
	onmessage: ((event: { data: string }) => void) | null = null
	onclose: ((event: { code: number }) => void) | null = null
	onerror: (() => void) | null = null

	constructor(readonly url: string) {
		FakeWebSocket.instances.push(this)
	}

	send(data: string): void {
		this.sent.push(data)
	}

	close(): void {
		this.readyState = FakeWebSocket.CLOSED
	}

	pings(): number {
		return this.sent.filter((raw) => raw.includes('"ping"')).length
	}

	pong(): void {
		this.onmessage?.({ data: JSON.stringify({ type: 'stream.pong' }) })
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

describe('event stream probe', () => {
	beforeEach(() => {
		FakeWebSocket.instances = []
		vi.stubGlobal('WebSocket', FakeWebSocket)
		vi.useFakeTimers()
	})

	afterEach(() => {
		vi.useRealTimers()
		vi.unstubAllGlobals()
	})

	it('pings a live socket and leaves the connection alone once it pongs', async () => {
		const client = new EventStreamClient()
		const socket = await connectClient(client)

		client.probe()
		expect(socket.pings()).toBe(1)

		// answered probe + answered heartbeats: nothing is torn down
		socket.pong()
		for (let i = 0; i < 3; i++) {
			vi.advanceTimersByTime(4_000)
			socket.pong()
		}
		await flushMicrotasks()

		expect(client.state.status).toBe('connected')
		expect(FakeWebSocket.instances).toHaveLength(1)

		client.disconnect()
	})

	it('turns a zombie socket that never pongs into a drop and a reconnect', async () => {
		const client = new EventStreamClient()
		const transitions: string[][] = []
		client.onStatusChange((next, previous) => transitions.push([previous, next]))
		const socket = await connectClient(client)
		// the OS killed the socket without a close event: it still claims OPEN
		socket.onclose = null

		client.probe()
		expect(socket.pings()).toBe(1)
		expect(client.state.status).toBe('connected')

		// the pong never comes
		vi.advanceTimersByTime(8_000)
		expect(transitions).toContainEqual(['connected', 'reconnecting'])

		vi.advanceTimersByTime(1_000)
		await flushMicrotasks()
		expect(FakeWebSocket.instances).toHaveLength(2)

		FakeWebSocket.instances[1].onopen?.()
		expect(client.state.status).toBe('connected')

		client.disconnect()
	})

	it('rebuilds a socket that is not open instead of waiting out the backoff', async () => {
		const client = new EventStreamClient()
		const socket = await connectClient(client)

		socket.readyState = FakeWebSocket.CLOSED
		socket.onclose?.({ code: 1006 })
		expect(client.state.status).toBe('reconnecting')

		client.probe()
		await flushMicrotasks()

		// no timer advanced: the probe reconnected now
		expect(FakeWebSocket.instances).toHaveLength(2)

		client.disconnect()
	})

	it('stays quiet after an intentional disconnect', async () => {
		const client = new EventStreamClient()
		await connectClient(client)
		client.disconnect()

		client.probe()
		await flushMicrotasks()

		expect(FakeWebSocket.instances).toHaveLength(1)
		expect(client.state.status).toBe('disconnected')
	})
})
