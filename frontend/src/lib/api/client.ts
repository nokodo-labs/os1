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
let authGeneration = 0
let logoutInProgress = false

export async function refreshAccessToken(): Promise<string | null> {
	if (logoutInProgress) return null
	if (refreshInFlight) return refreshInFlight

	const generation = authGeneration
	refreshInFlight = (async () => {
		try {
			const { data, response } = await rawApi.POST('/v1/auth/refresh', {})
			if (logoutInProgress || generation !== authGeneration) return null
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
			pathname =
				new URL(request.url).pathname +
				new URL(request.url).search +
				new URL(request.url).hash
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

		return request
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
 * unwraps Request objects back into URL + Blob fetches so normal POST bodies are not
 * mistaken for ReadableStream uploads by browser fetch implementations.
 *
 * why this is required:
 * 1. openapi-fetch internally wraps payloads into a `new Request(input)` object.
 * 2. According to the Fetch API, reading `Request.body` exposes it as a `ReadableStream`.
 * 3. Chromium rejects HTTP request streams without HTTP/2.
 * 4. Safari does not support fetch request streams even on HTTPS.
 *
 * We do not intentionally stream request bodies from the frontend, so materializing the
 * body as a Blob preserves behavior while avoiding browser-specific stream upload paths.
 */
async function safeFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	const urlStr =
		typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url

	if (!(input instanceof Request)) {
		return fetch(input, init)
	}

	const options: RequestInit = {
		...init,
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

	return fetch(urlStr, options)
}

export const rawApi = createClient<ApiPaths>({
	baseUrl: '',
	fetch: safeFetch,
	credentials: 'include',
})
rawApi.use(urlInterceptor)

export const api = createClient<ApiPaths>({ baseUrl: '', fetch: safeFetch, credentials: 'include' })
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
	logoutInProgress = true
	authGeneration += 1
	try {
		await rawApi.POST('/v1/auth/logout', {}).catch(() => {})
	} finally {
		clearAccessToken()
		logoutInProgress = false
	}
}
