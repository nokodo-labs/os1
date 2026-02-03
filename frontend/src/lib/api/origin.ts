import { browser } from '$app/environment'

import { loadPublicConfig } from '$lib/config/public'

let apiOrigin: string | null = null

function defaultApiOrigin(): string {
	if (!browser) return ''

	const portFromEnv = Number.parseInt(import.meta.env.VITE_API_PORT || '', 10)
	const apiPort = Number.isFinite(portFromEnv) ? portFromEnv : 1383
	return `${window.location.protocol}//${window.location.hostname}:${apiPort}`
}

export function getApiOrigin(): string {
	return apiOrigin ?? defaultApiOrigin()
}

export function setApiOrigin(origin: string | null): void {
	apiOrigin = origin
}

// runs immediately on import
export const apiOriginReady: Promise<string | null> = (async () => {
	const config = await loadPublicConfig()
	setApiOrigin(config.api_origin)
	return getApiOrigin() || null
})()
