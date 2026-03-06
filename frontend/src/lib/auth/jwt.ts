function base64UrlToUtf8(input: string): string {
	const normalized = input.replace(/-/g, '+').replace(/_/g, '/')
	const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
	return decodeURIComponent(
		Array.from(atob(padded))
			.map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
			.join('')
	)
}

export function decodeJwtPayload(token: string): Record<string, unknown> | null {
	const parts = token.split('.')
	if (parts.length < 2) return null

	try {
		const payload = base64UrlToUtf8(parts[1])
		return JSON.parse(payload) as Record<string, unknown>
	} catch {
		return null
	}
}

export function getJwtUserId(token: string): string | null {
	const payload = decodeJwtPayload(token)
	const candidate = payload?.sub ?? payload?.user_id ?? payload?.uid
	return typeof candidate === 'string' && candidate.length > 0 ? candidate : null
}

export function getJwtEmail(token: string): string | null {
	const payload = decodeJwtPayload(token)
	const candidate = payload?.email ?? payload?.preferred_username
	return typeof candidate === 'string' && candidate.length > 0 ? candidate : null
}
