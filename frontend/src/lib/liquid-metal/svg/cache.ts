interface DisplacementCacheEntry {
	imageDataUrl: string
	maxDisplacement: number
	scale: number
	timestamp: number
}

interface SpecularCacheEntry {
	imageDataUrl: string
	timestamp: number
}

const displacementCache = new Map<string, DisplacementCacheEntry>()
const specularCache = new Map<string, SpecularCacheEntry>()
const MAX_CACHE_SIZE = 50
const MAX_AGE_MS = 5 * 60 * 1000

export function getCachedDisplacementMap(key: string): DisplacementCacheEntry | null {
	const entry = displacementCache.get(key)
	if (!entry) return null

	if (Date.now() - entry.timestamp > MAX_AGE_MS) {
		displacementCache.delete(key)
		return null
	}

	return entry
}

export function setCachedDisplacementMap(
	key: string,
	entry: Omit<DisplacementCacheEntry, 'timestamp'>
): void {
	if (displacementCache.size >= MAX_CACHE_SIZE) {
		const oldestKey = displacementCache.keys().next().value
		if (oldestKey !== undefined) displacementCache.delete(oldestKey)
	}

	displacementCache.set(key, {
		...entry,
		timestamp: Date.now(),
	})
}

export function getCachedSpecularMap(key: string): SpecularCacheEntry | null {
	const entry = specularCache.get(key)
	if (!entry) return null

	if (Date.now() - entry.timestamp > MAX_AGE_MS) {
		specularCache.delete(key)
		return null
	}

	return entry
}

export function setCachedSpecularMap(
	key: string,
	entry: Omit<SpecularCacheEntry, 'timestamp'>
): void {
	if (specularCache.size >= MAX_CACHE_SIZE) {
		const oldestKey = specularCache.keys().next().value
		if (oldestKey !== undefined) specularCache.delete(oldestKey)
	}

	specularCache.set(key, {
		...entry,
		timestamp: Date.now(),
	})
}

export function clearCache(): void {
	displacementCache.clear()
	specularCache.clear()
}
