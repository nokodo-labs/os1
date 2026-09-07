/**
 * Enterprise-grade WebSocket client for real-time event streaming.
 * WS /v1/events/stream
 *
 * Authentication: uses httpOnly refresh_token cookie (auto-sent by browser).
 * No token in URL for security (avoids logging/history exposure).
 *
 * Reliability features:
 * - infinite reconnect with exponential backoff + jitter (never gives up)
 * - heartbeat ping every 4s with an 8s pong timeout (detects dead connections)
 * - probe() on network recovery / tab focus: pings a socket that claims OPEN and
 *   reconnects one that does not, so a zombie socket surfaces as a real drop
 * - clean state machine: disconnected → connecting → connected ↔ reconnecting
 *
 * Native Svelte 5 rune-based state (no svelte/store).
 */

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
type SessionRevokedHandler = () => void
type PrefixEventHandler = { prefixes: readonly string[]; handler: EventHandler }
type TypeEventHandlers = { type: string; handlers: EventHandler[] }

function addUnique<T>(items: T[], item: T): void {
	if (!items.includes(item)) items.push(item)
}

function removeItem<T>(items: T[], item: T): void {
	const index = items.indexOf(item)
	if (index !== -1) items.splice(index, 1)
}

function uniqueStrings(values: readonly string[]): string[] {
	const unique: string[] = []
	for (const value of values) addUnique(unique, value)
	return unique
}

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
	private handlers: EventHandler[] = []
	private typeHandlers: TypeEventHandlers[] = []
	private prefixHandlers: PrefixEventHandler[] = []
	private statusHandlers: StatusChangeHandler[] = []
	private sessionRevokedHandlers: SessionRevokedHandler[] = []
	private intentionalDisconnect = false
	private awaitingPong = false
	private connecting = false

	// browser event handlers (bound so we can remove them)
	private readonly onOnline = () => this.handleNetworkOnline()
	private readonly onVisibilityChange = () => this.handleVisibilityChange()

	readonly state = $state({
		status: 'connecting' as ConnectionStatus,
		/** WS session_id assigned by the server on stream.connected */
		sessionId: null as string | null,
		/**
		 * epoch ms when the current non-connected phase began, or null while
		 * connected.
		 */
		statusSince: Date.now() as number | null,
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

	/**
	 * manually force an immediate reconnect attempt.
	 * cancels any pending backoff timer and reconnects now, keeping the status
	 * timer running.
	 */
	reconnect(): void {
		this.intentionalDisconnect = false
		this.isConnected = true
		this.reconnectAttempts = 0
		this.cleanup()
		this.addBrowserListeners()
		void this.doConnect()
	}

	subscribe(handler: EventHandler): () => void {
		addUnique(this.handlers, handler)
		return () => removeItem(this.handlers, handler)
	}

	subscribeTypes(types: readonly string[], handler: EventHandler): () => void {
		const uniqueTypes = uniqueStrings(types)
		for (const type of uniqueTypes) {
			let entry = this.typeHandlers.find((typeEntry) => typeEntry.type === type)
			if (!entry) {
				entry = { type, handlers: [] }
				this.typeHandlers.push(entry)
			}
			addUnique(entry.handlers, handler)
		}
		return () => {
			for (const type of uniqueTypes) {
				const entry = this.typeHandlers.find((typeEntry) => typeEntry.type === type)
				if (!entry) continue
				removeItem(entry.handlers, handler)
				if (entry.handlers.length === 0) removeItem(this.typeHandlers, entry)
			}
		}
	}

	subscribePrefixes(prefixes: readonly string[], handler: EventHandler): () => void {
		const entry = { prefixes: uniqueStrings(prefixes), handler }
		addUnique(this.prefixHandlers, entry)
		return () => removeItem(this.prefixHandlers, entry)
	}

	/**
	 * ask the server for a pong right now, and rebuild the socket if there is
	 * none.
	 *
	 * on mobile the OS kills the socket while the app is backgrounded without
	 * ever delivering a close event, so `readyState` can still read OPEN over a
	 * dead connection. call this on any resume signal: a live socket answers and
	 * nothing happens, a zombie one runs out the pong timeout and reconnects,
	 * which is what marks the gap.
	 */
	probe(): void {
		if (!this.isConnected || this.intentionalDisconnect || this.connecting) return
		if (this.ws?.readyState === WebSocket.OPEN) {
			// a ping is already outstanding: its deadline is armed, leave it be
			if (!this.awaitingPong) this.sendPing()
			return
		}
		// no socket to probe - stop waiting out the backoff and rebuild it now
		this.reconnectAttempts = 0
		this.cleanup()
		void this.doConnect()
	}

	/** subscribe to connection status changes (e.g. for cache invalidation). */
	onStatusChange(handler: StatusChangeHandler): () => void {
		addUnique(this.statusHandlers, handler)
		return () => removeItem(this.statusHandlers, handler)
	}

	/** subscribe to server-side session revocation (close codes 4001 / 4002). */
	onSessionRevoked(handler: SessionRevokedHandler): () => void {
		addUnique(this.sessionRevokedHandlers, handler)
		return () => removeItem(this.sessionRevokedHandlers, handler)
	}

	/** update status and notify status change handlers. */
	private setStatus(status: ConnectionStatus): void {
		const previous = this.state.status
		if (previous === status) return
		// anchor the status timer: clear it once connected, otherwise start it when
		// leaving 'connected' (kept running across connecting<->reconnecting hops).
		if (status === 'connected') {
			this.state.statusSince = null
		} else if (previous === 'connected' || this.state.statusSince === null) {
			this.state.statusSince = Date.now()
		}
		this.state.status = status
		for (const handler of [...this.statusHandlers]) handler(status, previous)
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

				for (const handler of [...this.handlers]) handler(message)
				const typeEntry = this.typeHandlers.find((entry) => entry.type === message.type)
				if (typeEntry) {
					for (const handler of [...typeEntry.handlers]) handler(message)
				}
				for (const { prefixes, handler } of [...this.prefixHandlers]) {
					if (prefixes.some((prefix) => message.type.startsWith(prefix))) handler(message)
				}
			} catch {
				// ignore malformed
			}
		}

		this.ws.onclose = (event) => {
			this.connecting = false
			this.stopPing()
			this.clearPongTimeout()

			if (event.code === 4001 || event.code === 4002 || event.code === 4003) {
				// 4001 = unauthorized, 4002 = session revoked, 4003 = origin not allowed
				this.setStatus('disconnected')
				this.isConnected = false
				// 4001 and 4002 both mean this session's credential is dead and the
				// socket is never rebuilt: hand both to the hard-logout path rather
				// than leaving a silently dead stream behind.
				if (event.code === 4001 || event.code === 4002) {
					for (const handler of [...this.sessionRevokedHandlers]) handler()
				}
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

	// reconnect (infinite with exponential backoff + jitter)

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

	// heartbeat (ping / pong timeout)

	private startPing(): void {
		this.stopPing()
		this.pingIntervalId = setInterval(() => this.sendPing(), PING_INTERVAL_MS)
	}

	/** arm the pong deadline first, so even a throwing send is caught by it. */
	private sendPing(): void {
		if (this.ws?.readyState !== WebSocket.OPEN) return
		this.awaitingPong = true
		this.startPongTimeout()
		try {
			this.ws.send(JSON.stringify({ type: 'ping' }))
		} catch {
			// send failed - the pong timeout above catches it
		}
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

	// browser event listeners (network recovery, tab focus)

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
		this.probe()
	}

	private handleVisibilityChange(): void {
		if (document.visibilityState !== 'visible') return
		this.probe()
	}

	// cleanup

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
