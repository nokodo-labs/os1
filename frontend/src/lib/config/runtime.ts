/**
 * Runtime configuration loader.
 *
 * SSG/Prerender notes:
 * - During prerender (adapter-static), there is no browser and relative fetches fail.
 * - We return a deterministic fallback during SSR/prerender so pages can be statically generated.
 * - The real config is loaded client-side on hydration via loadPublicConfig() + API call.
 */
import { browser } from '$app/environment'

import { api } from '$lib/api/index'
import { setV1ApiOrigin } from '$lib/api/v1/client'
import { loadPublicConfig } from '$lib/config/public'

type RuntimeConfig = Awaited<ReturnType<typeof api.getRuntimeConfig>>

/** Fallback config used during SSR/prerender or when config.json is unavailable. */
const FALLBACK_CONFIG: RuntimeConfig = Object.freeze({
	frontend_origin: null,
	cdn_origin: null,
})

let runtimeConfigPromise: Promise<RuntimeConfig> | null = null
let runtimeConfig: RuntimeConfig | null = null

export async function initRuntimeConfig(): Promise<RuntimeConfig> {
	if (runtimeConfigPromise) return runtimeConfigPromise

	runtimeConfigPromise = (async (): Promise<RuntimeConfig> => {
		// SSR/prerender: no browser, no fetch — return deterministic fallback
		if (!browser) {
			setV1ApiOrigin(import.meta.env.VITE_API_ORIGIN || null)
			runtimeConfig = FALLBACK_CONFIG
			return FALLBACK_CONFIG
		}

		try {
			const publicConfig = await loadPublicConfig()
			setV1ApiOrigin(publicConfig.api_origin)
			const data = await api.getRuntimeConfig()
			runtimeConfig = data
			return data
		} catch {
			// Fallback: use build-time origin if config.json or API is unavailable
			setV1ApiOrigin(import.meta.env.VITE_API_ORIGIN || null)
			runtimeConfig = FALLBACK_CONFIG
			return FALLBACK_CONFIG
		}
	})()

	return runtimeConfigPromise
}

export function getRuntimeConfigSync(): RuntimeConfig | null {
	return runtimeConfig
}

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
	return initRuntimeConfig()
}

export function buildAssetUrl(path: string): string {
	const normalizedPath = path.startsWith('/') ? path : `/${path}`
	const cdnOrigin = runtimeConfig?.cdn_origin
	if (!cdnOrigin) return normalizedPath
	return `${cdnOrigin.replace(/\/+$/, '')}${normalizedPath}`
}
