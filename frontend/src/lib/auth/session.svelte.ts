import { browser } from '$app/environment'

/**
 * access token is stored in memory only (not localStorage).
 * this is intentional for security - the token lives only for the session lifetime.
 * refresh token is stored in an httpOnly cookie managed by the backend.
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

/** in-memory access token. cleared on page refresh (by design). */
let accessToken = $state<string | null>(null)

/**
 * auth readiness gate. the API client waits for this before making authenticated requests.
 * this ensures we don't fire requests before the layout has had a chance to refresh the token.
 */
let authReadyResolve: (() => void) | null = null
export const authReady: Promise<void> = browser
	? new Promise<void>((resolve) => {
			authReadyResolve = resolve
		})
	: Promise.resolve()

/** called by the layout after auth flow completes (token refreshed or determined unnecessary). */
export function markAuthReady(): void {
	authReadyResolve?.()
	authReadyResolve = null
}

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
