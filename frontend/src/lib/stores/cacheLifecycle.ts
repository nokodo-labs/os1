export type MaybePromise<T> = T | Promise<T>

export type CacheScope =
	| { kind: 'all' }
	| { kind: 'collection'; name?: string }
	| { kind: 'item'; id: string }
	| { kind: 'children'; parentId: string; childType?: string }
	| { kind: 'counts'; id?: string }
	| { kind: 'window'; startAt: string; endAt: string; includeCompleted?: boolean }
	| { kind: 'resource'; resourceType: string; resourceId: string; slice?: string }

export interface RefreshableStore<Scope = CacheScope> {
	id: string
	shouldRefresh?(): boolean
	refresh(scope?: Scope): MaybePromise<unknown>
}

export interface ApiCacheStore<Scope = CacheScope> extends RefreshableStore<Scope> {
	invalidate(scope?: Scope): void
	clear?(): void
	init?(): void
	cleanup?(): void
}

const REFRESH_CONCURRENCY = 4

export function invalidateApiCacheStores(stores: readonly ApiCacheStore[]): void {
	for (const store of stores) store.invalidate()
}

export function initApiCacheStores(stores: readonly ApiCacheStore[]): void {
	for (const store of stores) store.init?.()
}

export async function refreshLifecycleStores(stores: readonly RefreshableStore[]): Promise<void> {
	const remainingStores = [...stores]
	const workerCount = Math.min(REFRESH_CONCURRENCY, remainingStores.length)
	const workers = Array.from({ length: workerCount }, async () => {
		while (remainingStores.length > 0) {
			const store = remainingStores.shift()
			if (!store) return
			if (store.shouldRefresh && !store.shouldRefresh()) continue
			await Promise.resolve(store.refresh()).catch(() => undefined)
		}
	})

	await Promise.all(workers)
}

export function clearApiCacheStores(stores: readonly ApiCacheStore[]): void {
	for (const store of stores) store.clear?.()
}
