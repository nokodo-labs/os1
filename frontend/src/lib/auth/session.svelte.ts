import { browser } from '$app/environment'

/**
 * Access token is stored in memory only (not localStorage).
 * This is intentional for security — the token lives only for the session lifetime.
 * Refresh token is stored in an httpOnly cookie managed by the backend.
 */

const ACCESS_TOKEN_CHANGED_EVENT = 'auth:token-changed'

function emitAccessTokenChanged(token: string | null): void {
	if (!browser) return
	window.dispatchEvent(
		new CustomEvent(ACCESS_TOKEN_CHANGED_EVENT, {
			detail: { token },
		})
	)
}

/** In-memory access token. Cleared on page refresh (by design). */
export let accessToken = $state<string | null>(null)

export function onAccessTokenChanged(handler: (token: string | null) => void): () => void {
	if (!browser) return () => {}
	const listener = (event: Event) => {
		const custom = event as CustomEvent<{ token: string | null }>
		handler(custom.detail?.token ?? null)
	}
	window.addEventListener(ACCESS_TOKEN_CHANGED_EVENT, listener)
	return () => window.removeEventListener(ACCESS_TOKEN_CHANGED_EVENT, listener)
}

export function getAccessToken(): string | null {
	return accessToken
}

export function setAccessToken(token: string): void {
	if (!browser) return
	if (token === accessToken) return
	accessToken = token
	emitAccessTokenChanged(token)
}

export function clearAccessToken(): void {
	if (!browser) return
	if (accessToken === null) return
	accessToken = null
	emitAccessTokenChanged(null)
}

export function isLoggedIn(): boolean {
	return Boolean(accessToken)
}
