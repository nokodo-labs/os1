import { loadPublicConfig } from '$lib/config/public'

let apiOrigin: string | null = null

export function getApiOrigin(): string {
	return apiOrigin ?? ''
}

export function setApiOrigin(origin: string | null): void {
	apiOrigin = origin
}

// runs immediately on import
export const apiOriginReady: Promise<string | null> = (async () => {
	const config = await loadPublicConfig()
	setApiOrigin(config.api_origin)
	return config.api_origin
})()
