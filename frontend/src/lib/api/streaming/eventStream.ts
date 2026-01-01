/**
 * WebSocket client for real-time event streaming.
 * WS /events/stream?token=<jwt>
 *
 * Provides auto-reconnect, Svelte store integration, and event subscription.
 */

import { get, writable } from 'svelte/store'
import { buildApiBaseURL } from '../client'

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
	private handlers: Set<EventHandler> = new Set()
	private intentionalDisconnect = false

	readonly status = writable<ConnectionStatus>('disconnected')
	readonly lastEvent = writable<StreamMessage | null>(null)

	private buildWsUrl(token: string): string {
		const baseUrl = buildApiBaseURL(import.meta.env.VITE_API_ORIGIN)
		const wsBase = baseUrl.replace(/^http/, 'ws')
		return `${wsBase}/events/stream?token=${encodeURIComponent(token)}`
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
		this.status.set('disconnected')
	}

	subscribe(handler: EventHandler): () => void {
		this.handlers.add(handler)
		return () => this.handlers.delete(handler)
	}

	private doConnect(): void {
		if (!this.token) return

		const currentStatus = get(this.status)
		this.status.set(currentStatus === 'disconnected' ? 'connecting' : 'reconnecting')

		try {
			this.ws = new WebSocket(this.buildWsUrl(this.token))
		} catch {
			this.scheduleReconnect()
			return
		}

		this.ws.onopen = () => {
			this.status.set('connected')
			this.reconnectAttempts = 0
			this.startPing()
		}

		this.ws.onmessage = (event) => {
			try {
				const message = JSON.parse(event.data) as StreamMessage
				this.lastEvent.set(message)
				this.handlers.forEach((h) => h(message))
			} catch {
				// ignore malformed
			}
		}

		this.ws.onclose = (event) => {
			this.stopPing()
			if (event.code === 4001) {
				this.status.set('disconnected')
				this.token = null
				return
			}
			if (!this.intentionalDisconnect) {
				this.scheduleReconnect()
			} else {
				this.status.set('disconnected')
			}
		}

		this.ws.onerror = () => {}
	}

	private scheduleReconnect(): void {
		if (this.intentionalDisconnect) return
		if (this.reconnectAttempts >= this.maxReconnectAttempts) {
			this.status.set('disconnected')
			return
		}

		this.status.set('reconnecting')
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
