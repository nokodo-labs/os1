/**
 * collaborative editing provider - Yjs CRDT sync over existing event WS.
 *
 * manages a Yjs Doc per document, syncing binary updates through the
 * platform's event WebSocket. no extra connections needed.
 *
 * lifecycle:
 * 1. connect() -> sends doc.join, receives doc.state (full Yjs state)
 * 2. local edits -> Yjs update -> WS doc.update -> server -> peers
 * 3. remote updates arrive -> applied to local Yjs doc -> prosemirror renders
 * 4. disconnect() -> sends doc.leave -> cleans up
 *
 * the provider does NOT own the editor. it provides the Yjs Doc and
 * a SimpleAwareness instance compatible with yCursorPlugin from y-prosemirror.
 */

import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import * as Y from 'yjs'

// palette for remote cursor colors
const CURSOR_COLORS = [
	'#FF6B6B',
	'#4ECDC4',
	'#45B7D1',
	'#96CEB4',
	'#FFEAA7',
	'#DDA0DD',
	'#98D8C8',
	'#F7DC6F',
	'#BB8FCE',
	'#85C1E9',
]
function pickColor(): string {
	return CURSOR_COLORS[Math.floor(Math.random() * CURSOR_COLORS.length)]
}

export interface DocParticipant {
	userId: string
	sessionId: string
	userName?: string
	avatarUrl?: string | null
	color?: string
}

export interface CollaborationProviderOptions {
	documentId: string
	/** user info for awareness (cursor labels) */
	user?: { id: string; name: string; avatarUrl?: string | null }
	/** called when initial sync completes (safe to populate empty doc) */
	onSynced?: () => void
	/** called when participant list changes */
	onParticipantsChange?: (participants: DocParticipant[]) => void
}

// base64 helpers for Uint8Array <-> string
function encodeUpdate(update: Uint8Array): string {
	const binary = Array.from(update, (b) => String.fromCharCode(b)).join('')
	return btoa(binary)
}

function decodeUpdate(b64: string): Uint8Array {
	const binary = atob(b64)
	return Uint8Array.from(binary, (c) => c.charCodeAt(0))
}

// -- simple awareness (yCursorPlugin-compatible) --
// minimal implementation that mirrors the y-protocols Awareness interface
// enough for yCursorPlugin to render remote cursors.

type AwarenessChangeHandler = (
	changes: { added: number[]; updated: number[]; removed: number[] },
	origin: string
) => void

export class SimpleAwareness {
	readonly clientID: number
	private readonly _states = new Map<number, Record<string, unknown>>()
	// separate handler lists for 'change' and 'update' events
	// (y-protocols Awareness emits both; yCursorPlugin listens to 'change')
	private readonly _changeHandlers: AwarenessChangeHandler[] = []
	private readonly _updateHandlers: AwarenessChangeHandler[] = []

	constructor(doc: Y.Doc) {
		this.clientID = doc.clientID ?? Math.floor(Math.random() * 0xffffffff)
		this._states.set(this.clientID, {})
	}

	on(event: string, handler: AwarenessChangeHandler): void {
		if (event === 'change') this._changeHandlers.push(handler)
		else if (event === 'update') this._updateHandlers.push(handler)
	}

	off(event: string, handler: AwarenessChangeHandler): void {
		const list =
			event === 'change'
				? this._changeHandlers
				: event === 'update'
					? this._updateHandlers
					: null
		if (list) {
			const i = list.indexOf(handler)
			if (i !== -1) list.splice(i, 1)
		}
	}

	getLocalState(): Record<string, unknown> | null {
		return this._states.get(this.clientID) ?? null
	}

	getStates(): Map<number, Record<string, unknown>> {
		return this._states
	}

	setLocalStateField(field: string, value: unknown): void {
		let local = this._states.get(this.clientID)
		if (!local) {
			local = {}
			this._states.set(this.clientID, local)
		}
		local[field] = value
		const changes = { added: [], updated: [this.clientID], removed: [] }
		this._emit('change', changes, 'local')
		this._emit('update', changes, 'local')
	}

	/** apply a JSON-encoded awareness update from the server */
	applyUpdate(update: Uint8Array, origin: string): void {
		try {
			const str = new TextDecoder().decode(update)
			const obj = JSON.parse(str) as Record<string, Record<string, unknown>>
			const added: number[] = []
			const updated: number[] = []
			for (const [k, v] of Object.entries(obj)) {
				const id = Number(k)
				if (this._states.has(id)) {
					updated.push(id)
				} else {
					added.push(id)
				}
				this._states.set(id, v)
			}
			const changes = { added, updated, removed: [] }
			this._emit('change', changes, origin)
			this._emit('update', changes, origin)
		} catch {
			// ignore malformed awareness updates
		}
	}

	/** encode awareness state for clients as JSON Uint8Array */
	encodeUpdate(clients?: number[]): Uint8Array {
		const ids = clients ?? Array.from(this._states.keys())
		const obj: Record<number, Record<string, unknown>> = {}
		for (const id of ids) {
			const st = this._states.get(id)
			if (st) obj[id] = st
		}
		return new TextEncoder().encode(JSON.stringify(obj))
	}

	/** remove a remote client (e.g. on participant_left) */
	removeClient(clientId: number): void {
		if (this._states.has(clientId)) {
			this._states.delete(clientId)
			const changes = { added: [], updated: [], removed: [clientId] }
			this._emit('change', changes, 'remote')
			this._emit('update', changes, 'remote')
		}
	}

	/** remove all remote clients (cleanup) */
	removeAllRemoteClients(): void {
		const removed: number[] = []
		for (const id of this._states.keys()) {
			if (id !== this.clientID) removed.push(id)
		}
		for (const id of removed) this._states.delete(id)
		if (removed.length > 0) {
			const changes = { added: [], updated: [], removed }
			this._emit('change', changes, 'remote')
			this._emit('update', changes, 'remote')
		}
	}

	/** fire handlers for a given event, isolating each with try-catch */
	private _emit(
		event: 'change' | 'update',
		changes: { added: number[]; updated: number[]; removed: number[] },
		origin: string
	): void {
		const handlers = event === 'change' ? this._changeHandlers : this._updateHandlers
		for (const cb of handlers) {
			try {
				cb(changes, origin)
			} catch {
				// isolate handler exceptions so one failure never kills the chain
			}
		}
	}
}

export class CollaborationProvider {
	readonly doc: Y.Doc
	readonly awareness: SimpleAwareness
	private documentId: string
	private wsSessionId: string | null = null
	private unsubscribe: (() => void) | null = null
	private synced = false
	private participants: DocParticipant[] = []
	private options: CollaborationProviderOptions
	private destroyed = false
	private userColor: string

	// map ws session_id -> awareness clientID for remote cursors
	private sessionToClient = new Map<string, number>()
	private clientCounter = 1_000_000 // synthetic clientIDs start high to avoid collisions

	// periodic awareness heartbeat keeps cursor positions fresh even when
	// a single update is lost or when no user interaction triggers re-emission
	private heartbeatTimer: ReturnType<typeof setInterval> | null = null
	private static readonly HEARTBEAT_MS = 15_000

	constructor(options: CollaborationProviderOptions) {
		this.options = options
		this.documentId = options.documentId
		this.doc = new Y.Doc()
		this.awareness = new SimpleAwareness(this.doc)
		this.userColor = pickColor()

		// set local awareness (cursor label + color)
		if (options.user) {
			this.awareness.setLocalStateField('user', {
				name: options.user.name,
				color: this.userColor,
				id: options.user.id,
			})
		}

		// forward local Yjs updates to the server
		this.doc.on('update', (update: Uint8Array, origin: unknown) => {
			if (origin === 'remote' || this.destroyed) return
			eventStreamClient.send({
				type: 'doc.update',
				document_id: this.documentId,
				update: encodeUpdate(update),
			})
		})

		// forward local awareness changes to server
		this.awareness.on('change', ({ added, updated, removed }, origin) => {
			if (origin === 'server' || origin === 'remote' || this.destroyed) return
			const changedClients = [...added, ...updated, ...removed]
			const encoded = this.awareness.encodeUpdate(changedClients)
			eventStreamClient.send({
				type: 'doc.awareness',
				document_id: this.documentId,
				data: Array.from(encoded),
			})
		})
	}

	connect(): void {
		this.unsubscribe = eventStreamClient.subscribe((msg) => this.handleMessage(msg))

		// eagerly capture session_id from already-connected WS
		// (stream.connected was already dispatched before this provider existed)
		if (eventStreamClient.state.sessionId && !this.wsSessionId) {
			this.wsSessionId = eventStreamClient.state.sessionId
		}

		// if already connected, join immediately
		if (eventStreamClient.state.status === 'connected') {
			eventStreamClient.send({
				type: 'doc.join',
				document_id: this.documentId,
			})
		}

		// periodic heartbeat: re-broadcast local awareness so cursor positions
		// stay visible even if a single awareness message was lost
		this.heartbeatTimer = setInterval(() => {
			if (this.destroyed || !this.synced) return
			const encoded = this.awareness.encodeUpdate([this.awareness.clientID])
			eventStreamClient.send({
				type: 'doc.awareness',
				document_id: this.documentId,
				data: Array.from(encoded),
			})
		}, CollaborationProvider.HEARTBEAT_MS)
	}

	disconnect(): void {
		this.destroyed = true
		if (this.heartbeatTimer !== null) {
			clearInterval(this.heartbeatTimer)
			this.heartbeatTimer = null
		}
		if (eventStreamClient.state.status === 'connected') {
			eventStreamClient.send({
				type: 'doc.leave',
				document_id: this.documentId,
			})
		}
		this.unsubscribe?.()
		this.unsubscribe = null
		this.doc.destroy()
	}

	isSynced(): boolean {
		return this.synced
	}

	getSessionId(): string | null {
		return this.wsSessionId
	}

	getParticipants(): DocParticipant[] {
		return this.participants
	}

	private handleMessage(msg: StreamMessage): void {
		if (this.destroyed) return

		// on (re)connect, capture session_id and join
		if (msg.type === 'stream.connected') {
			const sessionId = msg.session_id
			if (typeof sessionId === 'string') {
				this.wsSessionId = sessionId
			}
			eventStreamClient.send({
				type: 'doc.join',
				document_id: this.documentId,
			})
			return
		}

		// filter messages to our document
		const docId = msg.document_id
		if (docId !== this.documentId) return

		switch (msg.type) {
			case 'doc.state':
				this.handleState(msg)
				break
			case 'doc.update':
				this.handleUpdate(msg)
				break
			case 'doc.participant_joined':
				this.handleParticipantJoined(msg)
				break
			case 'doc.participant_left':
				this.handleParticipantLeft(msg)
				break
			case 'doc.awareness':
				this.handleRemoteAwareness(msg)
				break
		}
	}

	private handleState(msg: StreamMessage): void {
		const stateB64 = msg.state
		if (typeof stateB64 !== 'string') return

		// capture session_id from doc.state (authoritative, always present)
		if (typeof msg.session_id === 'string') {
			this.wsSessionId = msg.session_id
		}

		const state = decodeUpdate(stateB64)
		Y.applyUpdate(this.doc, state, 'remote')
		this.synced = true

		const rawParticipants = msg.participants
		if (Array.isArray(rawParticipants)) {
			this.participants = rawParticipants.map((p) => ({
				userId: String(p.user_id ?? ''),
				sessionId: String(p.session_id ?? ''),
				userName: typeof p.user_name === 'string' ? p.user_name : undefined,
				avatarUrl: typeof p.avatar_url === 'string' ? p.avatar_url : null,
				color: typeof p.color === 'string' ? p.color : undefined,
			}))
		}

		// clean stale awareness data from previous sessions (e.g. after WS reconnect)
		// only keep synthetic clientIDs for sessions that appear in the server's
		// current participant list
		const activeSessionIds = new Set(this.participants.map((p) => p.sessionId))
		for (const [sid, clientId] of this.sessionToClient) {
			if (!activeSessionIds.has(sid)) {
				this.awareness.removeClient(clientId)
				this.sessionToClient.delete(sid)
			}
		}

		this.options.onSynced?.()
		this.options.onParticipantsChange?.(this.participants)

		// re-emit local awareness so peers immediately see our cursor after
		// (re)connect rather than waiting for the next user interaction
		const encoded = this.awareness.encodeUpdate([this.awareness.clientID])
		eventStreamClient.send({
			type: 'doc.awareness',
			document_id: this.documentId,
			data: Array.from(encoded),
		})
	}

	private handleUpdate(msg: StreamMessage): void {
		// skip our own echoed updates
		const senderSessionId = msg.sender_session_id
		if (typeof senderSessionId === 'string' && senderSessionId === this.wsSessionId) return

		const updateB64 = msg.update
		if (typeof updateB64 !== 'string') return

		const update = decodeUpdate(updateB64)
		Y.applyUpdate(this.doc, update, 'remote')
	}

	private handleParticipantJoined(msg: StreamMessage): void {
		const userId = msg.user_id
		const sessionId = msg.session_id
		if (typeof userId !== 'string' || typeof sessionId !== 'string') return

		// skip our own echoed join (send_to_users can echo to all user connections)
		if (sessionId === this.wsSessionId) return

		// deduplicate: skip if this sessionId is already in the list
		if (this.participants.some((p) => p.sessionId === sessionId)) return

		this.participants = [
			...this.participants,
			{
				userId,
				sessionId,
				userName: typeof msg.user_name === 'string' ? msg.user_name : undefined,
				avatarUrl: typeof msg.avatar_url === 'string' ? msg.avatar_url : null,
				color: typeof msg.color === 'string' ? msg.color : undefined,
			},
		]
		this.options.onParticipantsChange?.(this.participants)
	}

	private handleParticipantLeft(msg: StreamMessage): void {
		const sessionId = msg.session_id
		if (typeof sessionId !== 'string') return

		// remove awareness state for the departed client
		const clientId = this.sessionToClient.get(sessionId)
		if (clientId !== undefined) {
			this.awareness.removeClient(clientId)
			this.sessionToClient.delete(sessionId)
		}

		this.participants = this.participants.filter((p) => p.sessionId !== sessionId)
		this.options.onParticipantsChange?.(this.participants)
	}

	private handleRemoteAwareness(msg: StreamMessage): void {
		const sessionId = msg.session_id
		const rawData = msg.data
		if (typeof sessionId !== 'string' || !rawData) return
		// skip own echoed awareness
		if (sessionId === this.wsSessionId) return

		// assign a stable synthetic clientID for this remote session
		let clientId = this.sessionToClient.get(sessionId)
		if (clientId === undefined) {
			clientId = this.clientCounter++
			this.sessionToClient.set(sessionId, clientId)
		}

		// data comes as number[] (Array.from(Uint8Array)) from the server relay
		// but we also accept the raw JSON object approach
		if (Array.isArray(rawData)) {
			// decode the encoded awareness and remap to our synthetic clientID
			try {
				const bytes = new Uint8Array(rawData as number[])
				const str = new TextDecoder().decode(bytes)
				const obj = JSON.parse(str) as Record<string, Record<string, unknown>>
				// remap: the sender's original clientID -> our synthetic clientID
				const remapped: Record<number, Record<string, unknown>> = {}
				for (const v of Object.values(obj)) {
					remapped[clientId] = v
				}
				const encoded = new TextEncoder().encode(JSON.stringify(remapped))
				this.awareness.applyUpdate(new Uint8Array(encoded), 'server')
			} catch {
				// ignore malformed awareness
			}
		}
	}
}
