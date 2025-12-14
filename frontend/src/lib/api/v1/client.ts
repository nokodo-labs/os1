import createClient from 'openapi-fetch'

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
    return createClient<paths>({ baseUrl: getV1BaseUrl() })
}
