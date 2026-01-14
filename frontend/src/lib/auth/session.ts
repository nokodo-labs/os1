import { browser } from '$app/environment'

const ACCESS_TOKEN_KEY = 'access_token'

const ACCESS_TOKEN_CHANGED_EVENT = 'auth:token-changed'

function emitAccessTokenChanged(token: string | null): void {
	if (!browser) return
	window.dispatchEvent(
		new CustomEvent(ACCESS_TOKEN_CHANGED_EVENT, {
			detail: { token },
		})
	)
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
	if (!browser) return null
	return window.localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setAccessToken(token: string): void {
	if (!browser) return
	window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
	emitAccessTokenChanged(token)
}

export function clearAccessToken(): void {
	if (!browser) return
	window.localStorage.removeItem(ACCESS_TOKEN_KEY)
	emitAccessTokenChanged(null)
}

export function isLoggedIn(): boolean {
	return Boolean(getAccessToken())
}
