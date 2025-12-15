import { api } from '$lib/api'
import { setV1ApiOrigin } from '$lib/api/v1/client'
import { loadPublicConfig } from '$lib/config/public'

type RuntimeConfig = Awaited<ReturnType<typeof api.getRuntimeConfig>>

let runtimeConfigPromise: Promise<RuntimeConfig> | null = null
let runtimeConfig: RuntimeConfig | null = null

export async function initRuntimeConfig(): Promise<RuntimeConfig> {
	if (!runtimeConfigPromise) {
		runtimeConfigPromise = (async () => {
			const publicConfig = await loadPublicConfig()
			setV1ApiOrigin(publicConfig.api_origin)
			const data = await api.getRuntimeConfig()
			runtimeConfig = data
			return data
		})().catch(() => {
			// fallback: use build-time origin if config.json is missing
			setV1ApiOrigin(import.meta.env.VITE_API_ORIGIN || null)
			const fallback: RuntimeConfig = {
				frontend_origin: null,
				cdn_origin: null,
			}
			runtimeConfig = fallback
			return fallback
		})
	}

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
