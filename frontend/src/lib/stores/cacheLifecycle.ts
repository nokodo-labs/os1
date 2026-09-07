/**
 * store contract for API-backed cache stores.
 *
 * this module defines the registry-adapter types (`RefreshableStore`,
 * `ApiCacheStore`) and the helpers in `apiCacheRegistry.ts` that drive them. it
 * is the canonical reference for what a "correct" store must expose; see
 * `README.md` for the prose overview and per-store categories.
 *
 * two layers are involved:
 * - the registry adapter (the plain objects in `apiCacheStores`) implements the
 *   interfaces below and delegates to the real store instance.
 * - the store instance owns the data plus the reactive state signals described
 *   under "state-signal contract".
 *
 * ## lifecycle methods (store instance)
 * - init():       subscribe to the WS event stream. idempotent. optional for
 *                 stores whose WS wiring lives at module scope (notes, files).
 * - cleanup():    unsubscribe from the WS event stream. paired with init().
 * - load(...):    domain fetch / re-fetch. may take domain options and track its
 *                 own loaded scopes. sets the loaded-once signal on success only.
 * - invalidate(): mark cached data stale WITHOUT clearing it. rendered data must
 *                 stay visible (stale-while-revalidate). never refetches itself.
 * - refresh(...): refetch already-loaded scopes and swap fresh data in place.
 * - clear():      wipe all local state (revoke blob URLs, reset the loaded-once
 *                 signal). called on logout / token change.
 *
 * ## state-signal contract (consumer-facing)
 * a list/collection store MUST let a view tell these three states apart so it
 * never renders "empty" before the first load resolves:
 *   1. not-loaded / loading -> loader
 *   2. loaded + empty       -> empty state
 *   3. loaded + populated   -> the list
 *
 * to do that, every list/collection cache store exposes `hasLoaded`: a reactive
 * boolean that flips true after the first SUCCESSFUL load and stays true until
 * clear(). this is the ONE canonical name - no `isReady`/`ready`/`initialized`
 * variants. consumers gate the empty state on it:
 *
 *   {#if items.length === 0 && !store.hasLoaded}  loader
 *   {:else if items.length === 0}                 empty
 *   {:else}                                        list
 *
 * a transient failure (network error, missing token, expired cache) MUST NOT
 * present as "empty": keep prior data and leave `hasLoaded` untouched so the
 * view shows data or a loader, never a false empty state.
 *
 * two optional, SEPARATE signals some stores also expose (do not confuse with
 * `hasLoaded`):
 * - `isLoading` / `loading`: a fetch is in flight; drives refetch spinners. it
 *   starts false, so it MUST NOT be the sole gate for the empty state.
 * - `hydrated`: the in-memory cache is currently populated (fetchedAt != null);
 *   unlike `hasLoaded` it can flip back when the cache is dropped (e.g. notes on
 *   sort change). used to choose loader-vs-stale-data during a refetch.
 *
 * ## refresh gating
 * `shouldRefresh()` is REQUIRED on every registered store and lets the lifecycle
 * refetch only already-loaded stores on resume. list stores return `hasLoaded`;
 * stores with no loaded-once collection (`activeRuns`, `resourceAccess`) return
 * `true` (always refetch). the `hasLoaded` reference in each gate is also what
 * compile-enforces the signal's presence + name across stores.
 */

export type MaybePromise<T> = T | Promise<T>

export type CacheScope =
	| { kind: 'all' }
	| { kind: 'collection'; name?: string }
	| { kind: 'item'; id: string }
	| { kind: 'children'; parentId: string; childType?: string }
	| { kind: 'counts'; id?: string }
	| { kind: 'window'; startAt: string; endAt: string; includeCompleted?: boolean }
	| { kind: 'resource'; resourceType: string; resourceId: string; slice?: string }

/** a store the lifecycle can refetch (registry adapter shape). */
export interface RefreshableStore<Scope = CacheScope> {
	id: string
	/** true when the backing store has loaded once; gates resume refetch. */
	shouldRefresh?(): boolean
	/** refetch already-loaded scopes and swap fresh data in place. */
	refresh(scope?: Scope): MaybePromise<unknown>
}

/** registry adapter for an API-backed cache store. see module docstring. */
export interface ApiCacheStore<Scope = CacheScope> extends RefreshableStore<Scope> {
	/** required: gate resume refetch. list stores return `hasLoaded`; stores with
	 * no loaded-once collection return `true`. */
	shouldRefresh(): boolean
	/** mark cached data stale WITHOUT clearing rendered data. never refetches. */
	invalidate(scope?: Scope): void
	/** wipe all local state incl. the loaded-once signal (logout/token change). */
	clear?(): void
	/** subscribe to the WS event stream (idempotent). */
	init?(): void
	/** unsubscribe from the WS event stream. */
	cleanup?(): void
}

const REFRESH_CONCURRENCY = 4

export function invalidateApiCacheStores(stores: readonly ApiCacheStore[]): void {
	for (const store of stores) store.invalidate()
}

export function initApiCacheStores(stores: readonly ApiCacheStore[]): void {
	for (const store of stores) store.init?.()
}

/**
 * refresh stores concurrently, skipping any whose `shouldRefresh()` returns
 * false (not yet loaded). an absent `shouldRefresh` means "always refresh".
 */
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
