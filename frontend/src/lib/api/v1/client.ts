import createClient from 'openapi-fetch'

import { clearAccessToken, getAccessToken, setAccessToken } from '$lib/auth/session'
import type { paths } from '../types'

let apiOrigin: string | null = null

let refreshInFlight: Promise<string | null> | null = null

function v1RawClient() {
	return createClient<paths>({
		baseUrl: getV1BaseUrl(),
		fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
			const request = input instanceof Request ? input : new Request(input, init)
			return fetch(new Request(request, { credentials: 'include' }))
		},
	})
}

function normalizeOrigin(origin: string | null): string | null {
	if (!origin) return null
	return origin.replace(/\/+$/, '')
}

export function setV1ApiOrigin(origin: string | null): void {
	apiOrigin = normalizeOrigin(origin)
}

export function getV1BaseUrl(): string {
	// base url includes the api version because the v1 openapi schema paths are rooted at /.
	// this keeps /v1 non-configurable while still allowing v2 to exist in parallel.
	return apiOrigin ? `${apiOrigin}/v1` : '/v1'
}

export async function refreshV1AccessToken(): Promise<string | null> {
	if (refreshInFlight) return refreshInFlight

	refreshInFlight = (async () => {
		try {
			const { data, response } = await v1RawClient().POST('/auth/refresh', {})
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

export async function logoutV1(): Promise<void> {
	try {
		await v1RawClient().POST('/auth/logout', {})
	} catch {
		// best-effort: local logout still proceeds
	}
}

export function v1Client() {
	return createClient<paths>({
		baseUrl: getV1BaseUrl(),
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

			const refreshed = await refreshV1AccessToken()
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
