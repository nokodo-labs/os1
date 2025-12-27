const ACCESS_TOKEN_KEY = 'nokodo.access_token'

export function getAccessToken(): string | null {
	if (typeof window === 'undefined') return null
	return window.localStorage.getItem(ACCESS_TOKEN_KEY)
}

export function setAccessToken(token: string): void {
	if (typeof window === 'undefined') return
	window.localStorage.setItem(ACCESS_TOKEN_KEY, token)
}

export function clearAccessToken(): void {
	if (typeof window === 'undefined') return
	window.localStorage.removeItem(ACCESS_TOKEN_KEY)
}

export function isLoggedIn(): boolean {
	return Boolean(getAccessToken())
}
