/**
 * cache displacement maps to avoid regeneration
 * key format: `${width}-${height}-${bezelWidth}-${thickness}-${surfaceName}`
 */

interface CacheEntry {
	imageDataUrl: string
	maxDisplacement: number
	scale: number
	timestamp: number
}

const cache = new Map<string, CacheEntry>()
const MAX_CACHE_SIZE = 50
const MAX_AGE_MS = 5 * 60 * 1000

export function getCachedDisplacementMap(key: string): CacheEntry | null {
	const entry = cache.get(key)
	if (!entry) return null

	if (Date.now() - entry.timestamp > MAX_AGE_MS) {
		cache.delete(key)
		return null
	}

	return entry
}

export function setCachedDisplacementMap(key: string, entry: Omit<CacheEntry, 'timestamp'>) {
	if (cache.size >= MAX_CACHE_SIZE) {
		const oldestKey = cache.keys().next().value
		if (oldestKey !== undefined) cache.delete(oldestKey)
	}

	cache.set(key, {
		...entry,
		timestamp: Date.now(),
	})
}

export function clearCache() {
	cache.clear()
}
