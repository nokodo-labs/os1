/**
 * Enterprise-grade WebSocket client for real-time event streaming.
 * WS /v1/events/stream
 *
 * Authentication: uses httpOnly refresh_token cookie (auto-sent by browser).
 * No token in URL for security (avoids logging/history exposure).
 *
 * Reliability features:
 * - infinite reconnect with exponential backoff + jitter (never gives up)
 * - heartbeat ping every 15s with pong timeout (detects dead connections)
 * - automatic reconnect on network recovery (navigator.onLine)
 * - automatic reconnect on tab focus (visibilitychange)
 * - clean state machine: disconnected → connecting → connected ↔ reconnecting
 *
 * Native Svelte 5 rune-based state (no svelte/store).
 */

import { SvelteSet } from 'svelte/reactivity'
import { getApiBaseUrl } from '../client'
import { getSessionId } from '../sessionId'

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
	origin_session_id: string | null
}

type EventHandler = (message: StreamMessage) => void
type StatusChangeHandler = (newStatus: ConnectionStatus, previousStatus: ConnectionStatus) => void

/** how often to send a heartbeat ping (ms) */
// 4s keeps the connection alive under aggressive NAT/proxy idle timeouts (e.g. Docker virtual switch on Windows ~5s)
const PING_INTERVAL_MS = 4_000
/** how long to wait for pong before considering connection dead (ms) */
const PONG_TIMEOUT_MS = 8_000
/** minimum reconnect delay (ms) */
const RECONNECT_BASE_MS = 500
/** maximum reconnect delay (ms) */
const RECONNECT_MAX_MS = 30_000
/** after this many consecutive failures, we slow-tick but never stop */
const RECONNECT_SLOW_THRESHOLD = 20

export class EventStreamClient {
	private ws: WebSocket | null = null
	private isConnected = false
	private reconnectAttempts = 0
	private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null
	private pingIntervalId: ReturnType<typeof setInterval> | null = null
	private pongTimeoutId: ReturnType<typeof setTimeout> | null = null
	private handlers = new SvelteSet<EventHandler>()
	private statusHandlers = new SvelteSet<StatusChangeHandler>()
	private intentionalDisconnect = false
	private awaitingPong = false
	private connecting = false

	// browser event handlers (bound so we can remove them)
	private readonly onOnline = () => this.handleNetworkOnline()
	private readonly onVisibilityChange = () => this.handleVisibilityChange()

	readonly state = $state({
		status: 'disconnected' as ConnectionStatus,
		lastEvent: null as StreamMessage | null,
		/** WS session_id assigned by the server on stream.connected */
		sessionId: null as string | null,
	})

	private async buildWsUrl(): Promise<string> {
		const wsBase = getApiBaseUrl().replace(/^http/, 'ws')
		// send the per-tab session ID so the server reuses it as the WS
		// session identifier (same ID already sent as X-Session-ID on HTTP)
		const sid = encodeURIComponent(getSessionId())
		return `${wsBase}/v1/events/stream?session_id=${sid}`
	}

	/**
	 * Connect to the event stream.
	 * Authentication is handled via httpOnly cookie (auto-sent by browser).
	 */
	connect(): void {
		if (
			this.ws?.readyState === WebSocket.OPEN ||
			this.ws?.readyState === WebSocket.CONNECTING
		) {
			return
		}

		this.isConnected = true
		this.intentionalDisconnect = false
		this.reconnectAttempts = 0
		this.addBrowserListeners()
		void this.doConnect()
	}

	disconnect(): void {
		this.intentionalDisconnect = true
		this.cleanup()
		this.removeBrowserListeners()
		this.isConnected = false
		this.setStatus('disconnected')
	}

	subscribe(handler: EventHandler): () => void {
		this.handlers.add(handler)
		return () => this.handlers.delete(handler)
	}

	/** subscribe to connection status changes (e.g. for cache invalidation). */
	onStatusChange(handler: StatusChangeHandler): () => void {
		this.statusHandlers.add(handler)
		return () => this.statusHandlers.delete(handler)
	}

	/** update status and notify status change handlers. */
	private setStatus(status: ConnectionStatus): void {
		const previous = this.state.status
		if (previous === status) return
		this.state.status = status
		this.statusHandlers.forEach((h) => h(status, previous))
	}

	/** send a JSON message to the server (typing events, etc.) */
	send(message: Record<string, unknown>): void {
		if (this.ws?.readyState === WebSocket.OPEN) {
			try {
				this.ws.send(JSON.stringify(message))
			} catch {
				// send failure. pong timeout will catch dead connections
			}
		}
	}

	// connection lifecycle

	private async doConnect(): Promise<void> {
		if (!this.isConnected || this.connecting) return
		this.connecting = true

		this.setStatus(this.reconnectAttempts === 0 ? 'connecting' : 'reconnecting')

		try {
			this.ws = new WebSocket(await this.buildWsUrl())
		} catch {
			this.connecting = false
			this.scheduleReconnect()
			return
		}

		this.ws.onopen = () => {
			this.connecting = false
			this.setStatus('connected')
			this.state.sessionId = getSessionId()
			this.reconnectAttempts = 0
			this.awaitingPong = false
			this.startPing()
		}

		this.ws.onmessage = (event) => {
			try {
				const message = JSON.parse(event.data) as StreamMessage

				// handle pong: clear the pong timeout
				if (message.type === 'stream.pong' || message.type === 'pong') {
					this.awaitingPong = false
					this.clearPongTimeout()
				}

				// capture session_id so providers created after WS open can read it
				if (message.type === 'stream.connected' && typeof message.session_id === 'string') {
					this.state.sessionId = message.session_id
				}

				this.state.lastEvent = message
				this.handlers.forEach((h) => h(message))
			} catch {
				// ignore malformed
			}
		}

		this.ws.onclose = (event) => {
			this.connecting = false
			this.stopPing()
			this.clearPongTimeout()

			if (event.code === 4001 || event.code === 4003) {
				// 4001 = unauthorized, 4003 = origin not allowed
				this.setStatus('disconnected')
				this.isConnected = false
				return
			}
			if (!this.intentionalDisconnect) {
				this.scheduleReconnect()
			} else {
				this.setStatus('disconnected')
			}
		}

		this.ws.onerror = () => {
			// errors always trigger onclose - no action needed here
		}
	}

	// ── reconnect (infinite with exponential backoff + jitter) ──────────────────

	private scheduleReconnect(): void {
		if (this.intentionalDisconnect) return

		this.setStatus('reconnecting')
		this.reconnectAttempts++

		// exponential backoff: 500, 1000, 2000, … capped at 30s
		// after many failures, lock to max delay (slow-tick, never stop)
		const exp = Math.min(this.reconnectAttempts - 1, RECONNECT_SLOW_THRESHOLD)
		const base = Math.min(RECONNECT_BASE_MS * Math.pow(2, exp), RECONNECT_MAX_MS)
		// add ±25% jitter to prevent thundering herd
		const jitter = base * (0.75 + Math.random() * 0.5)
		const delay = Math.round(jitter)

		this.reconnectTimeoutId = setTimeout(() => void this.doConnect(), delay)
	}

	// ── heartbeat (ping / pong timeout) ───────────────────────────────────────

	private startPing(): void {
		this.stopPing()
		this.pingIntervalId = setInterval(() => {
			if (this.ws?.readyState === WebSocket.OPEN) {
				try {
					this.ws.send(JSON.stringify({ type: 'ping' }))
					this.awaitingPong = true
					this.startPongTimeout()
				} catch {
					// send failed - pong timeout will catch it
				}
			}
		}, PING_INTERVAL_MS)
	}

	private stopPing(): void {
		if (this.pingIntervalId) {
			clearInterval(this.pingIntervalId)
			this.pingIntervalId = null
		}
	}

	private startPongTimeout(): void {
		// don't reset the deadline if we're already waiting for a pong.
		// this ensures the timeout fires PONG_TIMEOUT_MS after the FIRST
		// unanswered ping, not after the last one (repeated pings would
		// otherwise keep pushing the deadline and never detect a dead server).
		if (this.pongTimeoutId) return
		this.pongTimeoutId = setTimeout(() => {
			if (this.awaitingPong) {
				// server didn't respond - consider connection dead
				this.forceReconnect()
			}
		}, PONG_TIMEOUT_MS)
	}

	private clearPongTimeout(): void {
		if (this.pongTimeoutId) {
			clearTimeout(this.pongTimeoutId)
			this.pongTimeoutId = null
		}
	}

	/** forcibly tear down current socket and reconnect immediately */
	private forceReconnect(): void {
		if (this.intentionalDisconnect || !this.isConnected) return
		this.cleanup()
		this.scheduleReconnect()
	}

	// ── browser event listeners (network recovery, tab focus) ───────────────

	private addBrowserListeners(): void {
		if (typeof window === 'undefined') return
		window.addEventListener('online', this.onOnline)
		document.addEventListener('visibilitychange', this.onVisibilityChange)
	}

	private removeBrowserListeners(): void {
		if (typeof window === 'undefined') return
		window.removeEventListener('online', this.onOnline)
		document.removeEventListener('visibilitychange', this.onVisibilityChange)
	}

	private handleNetworkOnline(): void {
		if (!this.isConnected || this.intentionalDisconnect) return
		if (this.ws?.readyState === WebSocket.OPEN) return
		// network just came back - reconnect immediately
		this.reconnectAttempts = 0
		this.cleanup()
		void this.doConnect()
	}

	private handleVisibilityChange(): void {
		if (document.visibilityState !== 'visible') return
		if (!this.isConnected || this.intentionalDisconnect) return
		if (this.ws?.readyState === WebSocket.OPEN) return
		// tab became visible and socket is not open - reconnect immediately
		this.reconnectAttempts = 0
		this.cleanup()
		void this.doConnect()
	}

	// ── cleanup ─────────────────────────────────────────────────────────────

	private cleanup(): void {
		this.stopPing()
		this.clearPongTimeout()
		this.awaitingPong = false
		this.connecting = false
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
