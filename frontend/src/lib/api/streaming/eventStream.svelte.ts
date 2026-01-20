/**
 * WebSocket client for real-time event streaming.
 * WS /v1/events/stream?token=<jwt>
 *
 * Native Svelte 5 rune-based state (no svelte/store).
 */

import { SvelteSet } from 'svelte/reactivity'
import { getApiBaseUrl } from '../client'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

/**
 * Base interface for all stream messages.
 * The `type` field is the discriminator:
 * - `stream.*` for control messages (stream.connected, stream.pong)
 * - Everything else is a business event (notification.created, task.completed, etc.)
 */
export interface StreamMessage {
	type: string
	[key: string]: unknown
}

/**
 * A business event from the event stream.
 * Matches the Event model structure from the backend.
 */
export interface StreamEvent extends StreamMessage {
	id: string
	type: string
	scope: string
	scope_id: string | null
	data: Record<string, unknown>
	version: number
	user_id: string | null
	thread_id: string | null
	message_id: string | null
	task_id: string | null
	project_id: string | null
	created_at: string | null
}

type EventHandler = (message: StreamMessage) => void

export class EventStreamClient {
	private ws: WebSocket | null = null
	private token: string | null = null
	private reconnectAttempts = 0
	private maxReconnectAttempts = 10
	private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null
	private pingIntervalId: ReturnType<typeof setInterval> | null = null
	private handlers = new SvelteSet<EventHandler>()
	private intentionalDisconnect = false

	readonly state = $state({
		status: 'disconnected' as ConnectionStatus,
		lastEvent: null as StreamMessage | null,
	})

	private buildWsUrl(token: string): string {
		const configuredBaseUrl = getApiBaseUrl()
		const httpBase = configuredBaseUrl || window.location.origin
		const wsBase = httpBase.replace(/^http/, 'ws')
		return `${wsBase}/v1/events/stream?token=${encodeURIComponent(token)}`
	}

	connect(token: string): void {
		if (
			this.ws?.readyState === WebSocket.OPEN ||
			this.ws?.readyState === WebSocket.CONNECTING
		) {
			if (this.token === token) return
			this.disconnect()
		}

		this.token = token
		this.intentionalDisconnect = false
		this.reconnectAttempts = 0
		this.doConnect()
	}

	disconnect(): void {
		this.intentionalDisconnect = true
		this.cleanup()
		this.token = null
		this.state.status = 'disconnected'
	}

	subscribe(handler: EventHandler): () => void {
		this.handlers.add(handler)
		return () => this.handlers.delete(handler)
	}

	private doConnect(): void {
		if (!this.token) return

		this.state.status = this.state.status === 'disconnected' ? 'connecting' : 'reconnecting'

		try {
			this.ws = new WebSocket(this.buildWsUrl(this.token))
		} catch {
			this.scheduleReconnect()
			return
		}

		this.ws.onopen = () => {
			this.state.status = 'connected'
			this.reconnectAttempts = 0
			this.startPing()
		}

		this.ws.onmessage = (event) => {
			try {
				const message = JSON.parse(event.data) as StreamMessage
				this.state.lastEvent = message
				this.handlers.forEach((h) => h(message))
			} catch {
				// ignore malformed
			}
		}

		this.ws.onclose = (event) => {
			this.stopPing()
			if (event.code === 4001) {
				this.state.status = 'disconnected'
				this.token = null
				return
			}
			if (!this.intentionalDisconnect) {
				this.scheduleReconnect()
			} else {
				this.state.status = 'disconnected'
			}
		}

		this.ws.onerror = () => {}
	}

	private scheduleReconnect(): void {
		if (this.intentionalDisconnect) return
		if (this.reconnectAttempts >= this.maxReconnectAttempts) {
			this.state.status = 'disconnected'
			return
		}

		this.state.status = 'reconnecting'
		this.reconnectAttempts++

		const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 30000)
		this.reconnectTimeoutId = setTimeout(() => this.doConnect(), delay)
	}

	private startPing(): void {
		this.stopPing()
		this.pingIntervalId = setInterval(() => {
			if (this.ws?.readyState === WebSocket.OPEN) {
				try {
					this.ws.send(JSON.stringify({ type: 'ping' }))
				} catch {
					// ignore
				}
			}
		}, 30000)
	}

	private stopPing(): void {
		if (this.pingIntervalId) {
			clearInterval(this.pingIntervalId)
			this.pingIntervalId = null
		}
	}

	private cleanup(): void {
		this.stopPing()
		if (this.reconnectTimeoutId) {
			clearTimeout(this.reconnectTimeoutId)
			this.reconnectTimeoutId = null
		}
		if (this.ws) {
			this.ws.onopen = null
			this.ws.onmessage = null
			this.ws.onclose = null
			this.ws.onerror = null
			if (
				this.ws.readyState === WebSocket.OPEN ||
				this.ws.readyState === WebSocket.CONNECTING
			) {
				this.ws.close()
			}
			this.ws = null
		}
	}
}

export const eventStreamClient = new EventStreamClient()
