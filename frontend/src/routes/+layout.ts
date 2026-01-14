/**
 * Root layout configuration for SSG (adapter-static).
 *
 * Architecture notes:
 * - ssr=true allows SvelteKit to render HTML during the build (prerender).
 * - prerender=true prerenders all routes by default; dynamic routes opt-out individually.
 * - Auth redirects are handled CLIENT-SIDE (in +layout.svelte) to keep prerendered pages deterministic.
 * - This load function only initializes runtime config; it must be SSR/prerender-safe.
 */
import { initRuntimeConfig } from '$lib/config/runtime'

export const ssr = true
export const prerender = true

export const load = async () => {
	const config = await initRuntimeConfig()
	return { config }
}
