import { browser } from '$app/environment'
import { authReady, clearAccessToken, getAccessToken, setAccessToken } from '$lib/auth.svelte'
import createClient from 'openapi-fetch'
import type { paths } from './types'

type PrefixedPaths<P, Prefix extends string> = {
	[K in keyof P as K extends string ? `${Prefix}${K}` : never]: P[K]
}

export type ApiPaths = paths & PrefixedPaths<paths, '/v1'>

function getApiBase(): string {
	if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL
	if (!browser) return 'http://localhost:1383'
	const portFromEnv = Number.parseInt(import.meta.env.VITE_API_PORT || '', 10)
	const apiPort = Number.isFinite(portFromEnv) ? portFromEnv : 1383
	return `${window.location.protocol}//${window.location.hostname}:${apiPort}`
}

const DEFAULT_API_BASE = getApiBase()
export { DEFAULT_API_BASE }

// ── deduped refresh ──────────────────────────────────────────────────
let refreshInFlight: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
	if (refreshInFlight) return refreshInFlight

	refreshInFlight = (async () => {
		try {
			const { data, response } = await rawApi.POST('/v1/auth/refresh', {})
			if (!response.ok || !data?.access_token) {
				clearAccessToken()
				return null
			}
			setAccessToken(data.access_token)
			return data.access_token
		} finally {
			refreshInFlight = null
		}
	})()

	return refreshInFlight
}

// ── fetch wrappers ───────────────────────────────────────────────────

/** raw fetch: cookies included, no Authorization header, no auth gate. */
async function rawFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const req = input instanceof Request ? input : new Request(input, init)
	return fetch(new Request(req, { credentials: 'include' }))
}

/** authenticated fetch: waits for authReady, injects Bearer, retries once on 401. */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await authReady

	const req = input instanceof Request ? input : new Request(input, init)
	const retryReq = req.clone()

	const token = getAccessToken()
	const headers = new Headers(req.headers)
	if (token && !headers.has('Authorization')) {
		headers.set('Authorization', `Bearer ${token}`)
	}

	const res = await fetch(new Request(req, { headers, credentials: 'include' }))
	if (res.status !== 401) return res

	// 401 - try refreshing once
	const refreshed = await refreshAccessToken()
	if (!refreshed) return res

	const retryHeaders = new Headers(retryReq.headers)
	retryHeaders.set('Authorization', `Bearer ${refreshed}`)
	return fetch(new Request(retryReq, { headers: retryHeaders, credentials: 'include' }))
}

// ── clients ──────────────────────────────────────────────────────────

/** unauthenticated client - for login, register, refresh, logout, etc. */
export const rawApi = createClient<ApiPaths>({
	baseUrl: DEFAULT_API_BASE,
	fetch: rawFetch,
})

/** authenticated client - waits for auth, injects Bearer, auto-retries on 401. */
export const api = createClient<ApiPaths>({
	baseUrl: DEFAULT_API_BASE,
	fetch: authFetch,
})

/** throw if the openapi-fetch response has an error, otherwise return data. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function unwrap<T>(result: { data?: T; error?: any; response: Response }): T {
	if (result.error !== undefined) {
		const detail = result.error?.detail
		throw new Error(
			typeof detail === 'string' ? detail : `request failed (${result.response.status})`
		)
	}
	return result.data as T
}
