import createClient from 'openapi-fetch'

import { getAccessToken } from '$lib/auth/session'
import type { paths } from '../types'

let apiOrigin: string | null = null

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

export function v1Client() {
	return createClient<paths>({
		baseUrl: getV1BaseUrl(),
		fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
			const token = getAccessToken()
			if (!token) return fetch(input, init)

			const headers = new Headers(init?.headers)
			if (!headers.has('Authorization')) {
				headers.set('Authorization', `Bearer ${token}`)
			}

			if (input instanceof Request) {
				const nextRequest = new Request(input, { ...init, headers })
				return fetch(nextRequest)
			}

			return fetch(input, { ...init, headers })
		},
	})
}
