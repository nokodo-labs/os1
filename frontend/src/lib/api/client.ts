import {
	authReady,
	clearAccessToken,
	getAccessToken,
	setAccessToken,
} from '$lib/auth/session.svelte'
import createClient from 'openapi-fetch'
import { apiOriginReady, getApiOrigin } from './origin'
import { getSessionId } from './sessionId'
import type { paths } from './types'

export type ApiPaths = paths

export { getApiOrigin as getApiBaseUrl }

export class BackendUnreachableError extends Error {
	constructor() {
		super('backend unreachable')
		this.name = 'BackendUnreachableError'
	}
}

let refreshInFlight: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
	if (refreshInFlight) return refreshInFlight

	refreshInFlight = (async () => {
		try {
			const { data, response } = await rawApi.POST('/v1/auth/refresh', {})
			if (!response || !response.ok || !data?.access_token) {
				clearAccessToken()
				return null
			}
			setAccessToken(data.access_token)
			return data.access_token
		} catch {
			throw new BackendUnreachableError()
		} finally {
			refreshInFlight = null
		}
	})()

	return refreshInFlight
}

const urlInterceptor = {
	async onRequest({ request }: { request: Request }) {
		await apiOriginReady

		const origin = getApiOrigin()
		if (!origin) return request

		const base = origin.endsWith('/') ? origin.slice(0, -1) : origin
		let pathname: string
		try {
			pathname = new URL(request.url).pathname + new URL(request.url).search + new URL(request.url).hash
		} catch {
			pathname = request.url.startsWith('/') ? request.url : `/${request.url}`
		}

		return new Request(base + pathname, request)
	},
}

const authInterceptor = {
	async onRequest({ request }: { request: Request }) {
		await authReady

		const token = getAccessToken()
		if (token && !request.headers.has('Authorization')) {
			request.headers.set('Authorization', `Bearer ${token}`)
		}

		const sessionId = getSessionId()
		if (sessionId && !request.headers.has('X-Session-ID')) {
			request.headers.set('X-Session-ID', sessionId)
		}

		return new Request(request, { credentials: 'include' })
	},

	async onResponse({ request, response }: { request: Request; response: Response }) {
		if (response.status !== 401) return response

		const refreshed = await refreshAccessToken()
		if (!refreshed) return response

		request.headers.set('Authorization', `Bearer ${refreshed}`)
		return safeFetch(request)
	},
}

/**
 * bypasses Chrome's ALPN protocol crash by unwrapping Request objects back into primitive
 * strings and Blobs. This prevents Chrome from identifying the payload as a ReadableStream.
 * 
 * WHY IS THIS REQUIRED?
 * 1. openapi-fetch internally wraps all payloads into a `new Request(input)` object.
 * 2. According to the Fetch API, accessing `Request.body` exposes it as a `ReadableStream`.
 * 3. Chromium strictly mandates HTTP/2 for stream uploads natively (throwing ERR_ALPN_NEGOTIATION_FAILED if H2 is missing).
 * 4. Chromium REFUSES to negotiate HTTP/2 over cleartext (H2C).
 * 
 * Thus, any cross-origin POST with a body from Vite to a local development backend crashes instantly
 * in Chrome over HTTP. Unpacking the Request into a `fetch(url, blob)` circumvents Chromium's
 * stream detection perfectly natively.
 * 
 * This hack automatically bypasses itself if the request URL is HTTPS, meaning in production behind a
 * reverse proxy, it uses 100% native fetch.
 */
async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url

	// If the origin is HTTPS, the browser will seamlessly negotiate HTTP/2 via TLS ALPN.
	// We can safely use the native fetch directly without unwrapping.
	if (urlStr.startsWith('https://')) {
		return fetch(input, init)
	}

	let options: RequestInit = { ...init }

	if (input instanceof Request) {
		options = {
			method: input.method,
			headers: input.headers,
			signal: input.signal,
			credentials: input.credentials,
			referrer: input.referrer,
			mode: input.mode,
			cache: input.cache,
			redirect: input.redirect,
			integrity: input.integrity,
		}
		if (input.body) {
			options.body = await input.clone().blob()
		}
	}

	return fetch(urlStr, options)
}

export const rawApi = createClient<ApiPaths>({ baseUrl: '', fetch: safeFetch })
rawApi.use(urlInterceptor)

export const api = createClient<ApiPaths>({ baseUrl: '', fetch: safeFetch })
api.use(urlInterceptor)
api.use(authInterceptor)

export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
	if (result.error !== undefined) {
		const err = result.error as { detail?: unknown }
		const detail = err?.detail
		throw new Error(
			typeof detail === 'string' ? detail : `request failed (${result.response.status})`
		)
	}
	return result.data as T
}

/**
 * use this ONLY for custom manual fetch requests (like raw Blob downloads)
 * that bypass the api middleware.
 */
export async function getAuthHeaders(): Promise<HeadersInit> {
	await authReady
	const headers: Record<string, string> = {}

	const token = getAccessToken()
	if (token) headers['Authorization'] = `Bearer ${token}`

	const sessionId = getSessionId()
	if (sessionId) headers['X-Session-ID'] = sessionId

	return headers
}

export async function logout(): Promise<void> {
	await rawApi.POST('/v1/auth/logout', {}).catch(() => {})
}
