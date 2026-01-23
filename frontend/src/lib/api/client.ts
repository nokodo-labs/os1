import createClient from 'openapi-fetch'

import { clearAccessToken, getAccessToken, setAccessToken } from '$lib/auth/session.svelte'
import type { paths } from './types'

type PrefixedPaths<P, Prefix extends string> = {
	[K in keyof P as K extends string ? `${Prefix}${K}` : never]: P[K]
}

// today: v1 schema paths are rooted at / (e.g. /threads)
// goal: let call sites explicitly choose /v1/... while keeping type safety
export type ApiPaths = paths & PrefixedPaths<paths, '/v1'>

let apiOrigin: string | null = null

let refreshInFlight: Promise<string | null> | null = null

function normalizeOrigin(origin: string | null): string | null {
	if (!origin) return null
	return origin.replace(/\/+$/, '')
}

export function setApiOrigin(origin: string | null): void {
	apiOrigin = normalizeOrigin(origin)
}

/**
 * Base API url WITHOUT any version path.
 * - if set via runtime config: "https://api.example.com"
 * - if unset: "" (same-origin relative requests like "/v1/..." still work)
 */
export function getApiBaseUrl(): string {
	return apiOrigin ?? ''
}

function apiRawClient() {
	return createClient<ApiPaths>({
		baseUrl: getApiBaseUrl(),
		fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
			const request = input instanceof Request ? input : new Request(input, init)
			return fetch(new Request(request, { credentials: 'include' }))
		},
	})
}

export async function refreshAccessToken(): Promise<string | null> {
	if (refreshInFlight) return refreshInFlight

	refreshInFlight = (async () => {
		try {
			const { data, response } = await apiRawClient().POST('/v1/auth/refresh', {})
			if (!response.ok) {
				clearAccessToken()
				return null
			}

			const token = data?.access_token
			if (!token) {
				clearAccessToken()
				return null
			}

			setAccessToken(token)
			return token
		} finally {
			refreshInFlight = null
		}
	})()

	return refreshInFlight
}

export async function logout(): Promise<void> {
	try {
		await apiRawClient().POST('/v1/auth/logout', {})
	} catch {
		// best-effort: local logout still proceeds
	}
}

export function apiClient() {
	return createClient<ApiPaths>({
		baseUrl: getApiBaseUrl(),
		fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
			// openapi-fetch calls custom fetch with a fully-formed Request.
			// if we ignore that request's headers/body, we can accidentally drop
			// critical info like Content-Type and cause backend 422s.
			const baseRequest = input instanceof Request ? input : new Request(input, init)
			const retryBaseRequest = baseRequest.clone()

			const token = getAccessToken()
			const baseHeaders = new Headers(baseRequest.headers)
			if (token && !baseHeaders.has('Authorization')) {
				baseHeaders.set('Authorization', `Bearer ${token}`)
			}

			let res = await fetch(
				new Request(baseRequest, {
					headers: baseHeaders,
					credentials: 'include',
				})
			)
			if (res.status !== 401) return res

			const refreshed = await refreshAccessToken()
			if (!refreshed) return res

			const retryHeaders = new Headers(retryBaseRequest.headers)
			retryHeaders.set('Authorization', `Bearer ${refreshed}`)
			res = await fetch(
				new Request(retryBaseRequest, {
					headers: retryHeaders,
					credentials: 'include',
				})
			)
			return res
		},
	})
}
