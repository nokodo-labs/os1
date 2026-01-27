import {
	authReady,
	clearAccessToken,
	getAccessToken,
	setAccessToken,
} from '$lib/auth/session.svelte'
import createClient from 'openapi-fetch'
import { apiOriginReady, getApiOrigin } from './origin'
import type { paths } from './types'

type PrefixedPaths<P, Prefix extends string> = {
	[K in keyof P as K extends string ? `${Prefix}${K}` : never]: P[K]
}

export type ApiPaths = paths & PrefixedPaths<paths, '/v1'>

let refreshInFlight: Promise<string | null> | null = null

export { getApiOrigin as getApiBaseUrl }

async function rawFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	const req = input instanceof Request ? input : new Request(input, init)
	return fetch(new Request(req, { credentials: 'include' }))
}

async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
	await apiOriginReady
	// wait for auth flow to complete before making authenticated requests.
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

	const refreshed = await refreshAccessToken()
	if (!refreshed) return res

	const retryHeaders = new Headers(retryReq.headers)
	retryHeaders.set('Authorization', `Bearer ${refreshed}`)
	return fetch(new Request(retryReq, { headers: retryHeaders, credentials: 'include' }))
}

function rawClient() {
	return createClient<ApiPaths>({ baseUrl: getApiOrigin(), fetch: rawFetch })
}

export function apiClient() {
	return createClient<ApiPaths>({ baseUrl: getApiOrigin(), fetch: authFetch })
}

export async function refreshAccessToken(): Promise<string | null> {
	if (refreshInFlight) return refreshInFlight

	refreshInFlight = (async () => {
		try {
			const { data, response } = await rawClient().POST('/v1/auth/refresh', {})
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

export async function logout(): Promise<void> {
	await rawClient()
		.POST('/v1/auth/logout', {})
		.catch(() => {})
}
