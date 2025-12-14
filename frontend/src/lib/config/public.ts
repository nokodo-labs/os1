import type { PublicConfig } from './types'

function normalizeOrigin(origin: string | null): string | null {
    if (!origin) return null
    return origin.replace(/\/+$/, '')
}

export async function loadPublicConfig(): Promise<PublicConfig> {
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
        return { api_origin: normalizeOrigin(import.meta.env.VITE_API_ORIGIN || null) }
    }
}
