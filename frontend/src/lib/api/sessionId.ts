/**
 * per-tab session identifier.
 *
 * every browser tab gets a unique session id, sent as X-Session-ID on
 * every authenticated API request.  the backend echoes it on the WS
 * event envelope so the frontend can tell whether an event originated
 * from *this* tab or from another session.
 */

import type { StreamMessage } from './streaming'

let id: string | null = null

/** v4 UUID that works in non-secure contexts (http:// in dev). */
function generateId(): string {
	if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
	const b = crypto.getRandomValues(new Uint8Array(16))
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	const h = [...b].map((v) => v.toString(16).padStart(2, '0')).join('')
	return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

/** returns a stable, per-tab session identifier (lazily generated). */
export function getSessionId(): string {
	if (!id) id = generateId()
	return id
}

/**
 * returns true when the event's origin_session_id matches this tab.
 * useful for UI hints - NOT for skipping data updates.
 */
export function isOwnEvent(message: StreamMessage): boolean {
	const sid =
		(message.origin_session_id as string | undefined) ??
		((message.data as Record<string, unknown> | undefined)?.origin_session_id as
			| string
			| undefined)
	return sid != null && sid === id
}
