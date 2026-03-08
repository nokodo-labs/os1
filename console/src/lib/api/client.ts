import { authReady, clearAccessToken, getAccessToken, setAccessToken } from '$lib/auth.svelte'
import createClient from 'openapi-fetch'
import { apiOriginReady, getApiOrigin } from './origin'
import type { paths } from './types'

type PrefixedPaths<P, Prefix extends string> = {
	[K in keyof P as K extends string ? `${Prefix}${K}` : never]: P[K]
}

export type ApiPaths = paths & PrefixedPaths<paths, '/v1'>

export { getApiOrigin as getApiBaseUrl }

// rewrite the URL's origin to the resolved API origin
function resolvedUrl(req: Request): string {
	const origin = getApiOrigin()
	if (!origin) return req.url
	const url = new URL(req.url)
	return origin + url.pathname + url.search + url.hash
}

// deduped refresh
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

// fetch wrappers

/** raw fetch: cookies included, no Authorization header, no auth gate. */
async function rawFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	const req = input instanceof Request ? input : new Request(input, init)
	const url = resolvedUrl(req)
	return fetch(url, {
		method: req.method,
		headers: req.headers,
		body: req.body,
		credentials: 'include',
		// required by browsers when body is a ReadableStream
		...(req.body ? { duplex: 'half' } : {}),
	} as RequestInit)
}

/** authenticated fetch: waits for authReady, injects Bearer, retries once on 401. */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	await authReady

	const req = input instanceof Request ? input : new Request(input, init)
	const reqClone = req.clone()
	const url = resolvedUrl(req)

	const token = getAccessToken()
	const headers = new Headers(req.headers)
	if (token && !headers.has('Authorization')) {
		headers.set('Authorization', `Bearer ${token}`)
	}

	const res = await fetch(url, {
		method: req.method,
		headers,
		body: req.body,
		credentials: 'include',
		...(req.body ? { duplex: 'half' } : {}),
	} as RequestInit)
	if (res.status !== 401) return res

	// 401 - try refreshing once
	const refreshed = await refreshAccessToken()
	if (!refreshed) return res

	const retryHeaders = new Headers(reqClone.headers)
	retryHeaders.set('Authorization', `Bearer ${refreshed}`)
	return fetch(url, {
		method: reqClone.method,
		headers: retryHeaders,
		body: reqClone.body,
		credentials: 'include',
		...(reqClone.body ? { duplex: 'half' } : {}),
	} as RequestInit)
}

// clients

/** unauthenticated client - for login, register, refresh, logout, etc. */
export const rawApi = createClient<ApiPaths>({
	baseUrl: '',
	fetch: rawFetch,
})

/** authenticated client - waits for auth, injects Bearer, auto-retries on 401. */
export const api = createClient<ApiPaths>({
	baseUrl: '',
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
