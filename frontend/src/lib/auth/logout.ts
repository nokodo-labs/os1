import { goto } from '$app/navigation'
import { resolve } from '$app/paths'
import { logout as requestLogout } from '$lib/api/client'
import { apiCacheStores } from '$lib/stores/apiCacheRegistry'
import { clearApiCacheStores } from '$lib/stores/cacheLifecycle'
import { session } from '$lib/stores/session.svelte'

let logoutInFlight: Promise<void> | null = null

export function logoutAndRedirect(): Promise<void> {
	if (logoutInFlight) return logoutInFlight

	logoutInFlight = (async () => {
		await requestLogout()
		session.clear()
		clearApiCacheStores(apiCacheStores)
		await goto(resolve('/login'), { replaceState: true })
	})().finally(() => {
		logoutInFlight = null
	})

	return logoutInFlight
}
