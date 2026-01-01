import createClient from 'openapi-fetch'

import { clearAccessToken, getAccessToken, setAccessToken } from '$lib/auth/session'
import type { paths } from '../types'

let apiOrigin: string | null = null

let refreshInFlight: Promise<string | null> | null = null

function v1RawClient() {
	return createClient<paths>({
		baseUrl: getV1BaseUrl(),
		fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
			return fetch(input, {
				...init,
				credentials: 'include',
			})
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
			const token = getAccessToken()
			const headers = new Headers(init?.headers)
			if (token && !headers.has('Authorization')) {
				headers.set('Authorization', `Bearer ${token}`)
			}

			const nextInit: RequestInit = {
				...init,
				headers,
				credentials: 'include',
			}

			const doFetch = async (t: string | null): Promise<Response> => {
				const nextHeaders = new Headers(headers)
				if (t) nextHeaders.set('Authorization', `Bearer ${t}`)
				if (input instanceof Request) {
					return fetch(new Request(input, { ...nextInit, headers: nextHeaders }))
				}
				return fetch(input, { ...nextInit, headers: nextHeaders })
			}

			let res = await doFetch(token)
			if (res.status !== 401) return res

			const refreshed = await refreshV1AccessToken()
			if (!refreshed) return res
			res = await doFetch(refreshed)
			return res
		},
	})
}
