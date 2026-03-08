import { browser } from '$app/environment'

import type { PublicConfig } from './types'

function normalizeOrigin(origin: string | null): string | null {
	if (!origin) return null
	return origin.replace(/\/+$/, '')
}

export async function loadPublicConfig(): Promise<PublicConfig> {
	// build-time env takes precedence when present.
	const envOrigin = normalizeOrigin(import.meta.env.VITE_API_ORIGIN || null)
	if (envOrigin) return { api_origin: envOrigin }

	// no browser fetch available during SSR/prerender.
	if (!browser) return { api_origin: null }

	try {
		const response = await fetch('/config.json', {
			method: 'GET',
			headers: { Accept: 'application/json' },
		})

		if (!response.ok) {
			throw new Error('failed to load config.json')
		}

		const data = (await response.json()) as PublicConfig
		return { api_origin: normalizeOrigin(data.api_origin) }
	} catch {
		return { api_origin: null }
	}
}
