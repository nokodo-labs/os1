/**
 * UUID generation that works in non-secure contexts (http:// in dev).
 * crypto.randomUUID() is only available on HTTPS or localhost - this polyfill
 * falls back to getRandomValues() which works everywhere.
 */
export function generateUUID(): string {
	if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
	const b = crypto.getRandomValues(new Uint8Array(16))
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	const h = [...b].map((v) => v.toString(16).padStart(2, '0')).join('')
	return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}
