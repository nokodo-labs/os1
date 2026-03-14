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

type PrefixedPaths<P, Prefix extends string> = {
	[K in keyof P as K extends string ? `${Prefix}${K}` : never]: P[K]
}

export type ApiPaths = paths & PrefixedPaths<paths, '/v1'>

export { getApiOrigin as getApiBaseUrl }

export class BackendUnreachableError extends Error {
	constructor() {
		super('backend unreachable')
		this.name = 'BackendUnreachableError'
	}
}

function resolveUrlStr(input: RequestInfo | URL): string {
	const origin = getApiOrigin()
	let raw = ''
	if (typeof input === 'string') raw = input
	else if (input instanceof URL) raw = input.toString()
	else raw = input.url

	if (!origin) return raw
	if (raw.startsWith('http://') || raw.startsWith('https://')) return raw

	const base = origin.endsWith('/') ? origin.slice(0, -1) : origin
	const path = raw.startsWith('/') ? raw : `/${raw}`
	return base + path
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
			// Do not clear the token on network throw
			throw new BackendUnreachableError()
		} finally {
			refreshInFlight = null
		}
	})()

	return refreshInFlight
}

function resolveFetchInit(
	input: RequestInfo | URL,
	init?: RequestInit
): { url: string; fetchInit: RequestInit } {
	const url = resolveUrlStr(input)

	if (input instanceof Request) {
		const isStream = input.body instanceof ReadableStream
		return {
			url,
			fetchInit: {
				method: input.method,
				headers: new Headers(input.headers),
				body: input.body,
				credentials: 'include',
				...(isStream ? { duplex: 'half' } : {}),
				...init,
			} as RequestInit,
		}
	}

	const isStream = init?.body instanceof ReadableStream
	return {
		url,
		fetchInit: {
			credentials: 'include',
			...(isStream ? { duplex: 'half' } : {}),
			...init,
		} as RequestInit,
	}
}

async function rawFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	const { url, fetchInit } = resolveFetchInit(input, init)
	return fetch(url, fetchInit)
}

export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	await authReady

	const { url, fetchInit } = resolveFetchInit(input, init)
	const headers = new Headers(fetchInit.headers)

	const token = getAccessToken()
	if (token && !headers.has('Authorization')) {
		headers.set('Authorization', `Bearer ${token}`)
	}

	const sessionId = getSessionId()
	if (sessionId && !headers.has('X-Session-ID')) {
		headers.set('X-Session-ID', sessionId)
	}

	const attemptInit = { ...fetchInit, headers }

	// Open API Fetch allows retrying via cloning request, however cloning a stream body
	// can sometimes be problematic. By keeping the init dictionary, we can just regenerate the
	// fetch call without strictly creating Request clones that consume streams.
	const requestToFetch = new Request(url, attemptInit)

	// clone if possible strictly for retry, but typically refresh doesn't need to read body again
	let retryRequest: Request | null = null
	if (!attemptInit.body || typeof attemptInit.body === 'string') {
		retryRequest = requestToFetch.clone()
	}

	const res = await fetch(requestToFetch)
	if (res.status !== 401) return res

	const refreshed = await refreshAccessToken()
	if (!refreshed) return res

	if (!retryRequest) {
		// if we couldn't clone it (e.g. consumed stream), just reconstruct it.
		retryRequest = new Request(url, attemptInit)
	}

	const retryHeaders = new Headers(retryRequest.headers)
	retryHeaders.set('Authorization', `Bearer ${refreshed}`)

	return fetch(new Request(retryRequest, { headers: retryHeaders }))
}

export const rawApi = createClient<ApiPaths>({
	baseUrl: '',
	fetch: rawFetch,
})

export const api = createClient<ApiPaths>({
	baseUrl: '',
	fetch: authFetch,
})

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

export async function logout(): Promise<void> {
	await rawApi.POST('/v1/auth/logout', {}).catch(() => {})
}
