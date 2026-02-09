import { browser } from '$app/environment'
import { rawApi, refreshAccessToken } from '$lib/api'

type User = {
	id: string
	email: string
	display_name: string | null
	avatar_url: string | null
	is_active: boolean
	is_superuser: boolean
	created_at: string
	updated_at: string
}

function parseJwt(token: string) {
	try {
		return JSON.parse(atob(token.split('.')[1]))
	} catch {
		return null
	}
}

/**
 * In-memory access token.
 * Intentionally NOT in localStorage — cleared on page refresh by design.
 * Refresh token lives in an httpOnly cookie set by the backend.
 */
let accessToken = $state<string | null>(null)

/** Auth readiness gate — API requests wait for this before firing. */
let authReadyResolve: (() => void) | null = null
export const authReady: Promise<void> = browser
	? new Promise<void>((resolve) => {
			authReadyResolve = resolve
		})
	: Promise.resolve()

/** Called by the root layout after auth flow completes. */
export function markAuthReady(): void {
	authReadyResolve?.()
	authReadyResolve = null
}

export function getAccessToken(): string | null {
	return accessToken
}

export function setAccessToken(token: string): void {
	accessToken = token
}

export function clearAccessToken(): void {
	accessToken = null
}

class AuthState {
	user = $state<User | null>(null)
	isAuthenticated = $derived(!!accessToken)

	async login(email: string, password: string) {
		const formBody = new URLSearchParams({ username: email, password, scope: '' })
		const { data, error } = await rawApi.POST('/v1/auth/login/access-token', {
			body: { username: email, password, scope: '' },
			bodySerializer: () => formBody,
			headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
		})

		if (error || !data) throw new Error('login failed')
		setAccessToken(data.access_token)
		await this.fetchUser()
	}

	async restoreSession(): Promise<boolean> {
		const token = await refreshAccessToken()
		if (!token) return false
		await this.fetchUser()
		return true
	}

	async fetchUser() {
		if (!accessToken) return
		const decoded = parseJwt(accessToken)
		if (!decoded || !decoded.sub) return

		const userId = String(decoded.sub)
		const { data, error } = await rawApi.GET('/v1/users/{user_id}', {
			params: { path: { user_id: userId } },
			headers: { Authorization: `Bearer ${accessToken}` },
		})
		if (error || !data) {
			console.error('failed to fetch user')
			this.logout()
			return
		}
		this.user = data as User
	}

	async register(email: string, password: string) {
		await rawApi.POST('/v1/users', {
			body: {
				email,
				password,
				is_active: true,
				is_superuser: true,
			},
		})
	}

	async logout() {
		await rawApi.POST('/v1/auth/logout', {}).catch(() => {})
		clearAccessToken()
		this.user = null
	}
}

export const auth = new AuthState()
export type { User }
