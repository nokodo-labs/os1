/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

/**
 * nokodo service worker.
 *
 * caching strategies:
 * - precache: app shell (HTML, CSS, JS, fonts) - versioned by build hash
 * - cache-first: static assets (images, fonts from /static)
 * - network-first: API data calls (/v1/ except auth) - app manages its own TTL caching
 * - network-only: auth/sensitive routes (/v1/auth/*)
 * - offline fallback: serves /offline.html when network is unavailable
 */

import { build, files, prerendered, version } from '$service-worker'

declare const self: ServiceWorkerGlobalScope

const PRECACHE = `precache-v${version}`
const RUNTIME = `runtime-v${version}`

// runtime cache limits
const RUNTIME_MAX_ENTRIES = 128

// all assets produced by the build + static files + prerendered pages
const PRECACHE_ASSETS = [
	...new Set([
		...build,
		...files.filter((f) => !f.startsWith('/icons/')),
		...prerendered,
		'/offline.html',
	]),
]

// O(1) lookup for precache hits
const PRECACHE_SET = new Set(PRECACHE_ASSETS)

// patterns that must never be cached
const NETWORK_ONLY_PATTERNS = [
	/\/v1\/auth\//,
	/\/v1\/token/,
	/\/health$/,
	/\/v1\/openapi\.json$/,
	/\/runs\/[^/]+\/stream$/, // SSE streaming endpoints must never be cached
	/\/system\/manifest\.json$/, // manifest must always be fresh for PWA installability
]

// static asset extensions eligible for cache-first
const STATIC_ASSET_RE = /\.(png|jpg|jpeg|gif|webp|avif|svg|ico|woff2?|ttf|eot|otf)$/i

// install: precache app shell
self.addEventListener('install', (event) => {
	event.waitUntil(caches.open(PRECACHE).then((cache) => cache.addAll(PRECACHE_ASSETS)))
})

// activate: purge old caches, claim clients
self.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) =>
				Promise.all(
					keys
						.filter((key) => key !== PRECACHE && key !== RUNTIME)
						.map((key) => caches.delete(key))
				)
			)
			.then(() => self.clients.claim())
	)
})

// fetch: route to appropriate caching strategy
self.addEventListener('fetch', (event) => {
	const { request } = event
	const url = new URL(request.url)

	// only handle same-origin GET requests
	if (url.origin !== self.location.origin) return
	if (request.method !== 'GET') return

	// network-only for auth/sensitive routes
	if (NETWORK_ONLY_PATTERNS.some((re) => re.test(url.pathname))) return

	// API calls: network-first with cache fallback for offline.
	// the app has its own TTL-based caching layer (ThreadCache, stores, etc.)
	// so the SW should not serve stale data - only provide offline resilience.
	if (url.pathname.startsWith('/v1/')) {
		event.respondWith(networkFirst(request))
		return
	}

	// precached assets: cache-first (versioned by build hash)
	if (PRECACHE_SET.has(url.pathname)) {
		event.respondWith(cacheFirst(request, PRECACHE))
		return
	}

	// other static assets (images, fonts): cache-first with runtime cache
	if (STATIC_ASSET_RE.test(url.pathname)) {
		event.respondWith(cacheFirst(request, RUNTIME))
		return
	}

	// navigation requests: try network, fall back to cached shell or offline page
	if (request.mode === 'navigate') {
		event.respondWith(navigationHandler(request))
		return
	}
})

type PushNotificationAction = {
	action: string
	title: string
	icon_url?: string | null
}

type PushNotificationPayload = {
	title: string
	body?: string | null
	icon_url?: string | null
	image_url?: string | null
	badge_url?: string | null
	action_url?: string | null
	tag?: string | null
	data?: Record<string, unknown> | null
	actions?: PushNotificationAction[]
	require_interaction?: boolean | null
	silent?: boolean | null
	renotify?: boolean | null
}

type WebPushNotificationOptions = NotificationOptions & {
	image?: string
	actions?: Array<{ action: string; title: string; icon?: string }>
	renotify?: boolean
}

self.addEventListener('push', (event: PushEvent) => {
	event.waitUntil(showPushNotification(event))
})

self.addEventListener('notificationclick', (event: NotificationEvent) => {
	event.notification.close()
	event.waitUntil(openNotificationTarget(event.notification))
})

// caching strategy implementations

async function showPushNotification(event: PushEvent): Promise<void> {
	const payload = parsePushPayload(event)
	if (!payload) return
	if (await hasVisibleWindowClient()) return

	const data = payload.data ?? {}
	if (payload.action_url) data.action_url = payload.action_url
	const options: WebPushNotificationOptions = {
		body: payload.body ?? undefined,
		icon: payload.icon_url ?? undefined,
		image: payload.image_url ?? undefined,
		badge: payload.badge_url ?? undefined,
		tag: payload.tag ?? undefined,
		data,
		actions: (payload.actions ?? []).map((action) => ({
			action: action.action,
			title: action.title,
			icon: action.icon_url ?? undefined,
		})),
		requireInteraction: payload.require_interaction ?? undefined,
		silent: payload.silent ?? undefined,
		renotify: payload.renotify ?? undefined,
	}

	await self.registration.showNotification(payload.title, options)
}

function parsePushPayload(event: PushEvent): PushNotificationPayload | null {
	if (!event.data) return null
	try {
		const value = event.data.json()
		if (!isRecord(value)) return null
		const title = readString(value, 'title')
		if (!title) return null
		return {
			title,
			body: readNullableString(value, 'body'),
			icon_url: readNullableString(value, 'icon_url'),
			image_url: readNullableString(value, 'image_url'),
			badge_url: readNullableString(value, 'badge_url'),
			action_url: readNullableString(value, 'action_url'),
			tag: readNullableString(value, 'tag'),
			data: readRecord(value, 'data'),
			actions: readActions(value, 'actions'),
			require_interaction: readNullableBoolean(value, 'require_interaction'),
			silent: readNullableBoolean(value, 'silent'),
			renotify: readNullableBoolean(value, 'renotify'),
		}
	} catch {
		return null
	}
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readString(record: Record<string, unknown>, key: string): string | undefined {
	const value = record[key]
	return typeof value === 'string' ? value : undefined
}

function readNullableString(record: Record<string, unknown>, key: string): string | null {
	const value = record[key]
	return typeof value === 'string' ? value : null
}

function readNullableBoolean(record: Record<string, unknown>, key: string): boolean | null {
	const value = record[key]
	return typeof value === 'boolean' ? value : null
}

function readRecord(record: Record<string, unknown>, key: string): Record<string, unknown> | null {
	const value = record[key]
	return isRecord(value) ? value : null
}

function readActions(record: Record<string, unknown>, key: string): PushNotificationAction[] {
	const value = record[key]
	if (!Array.isArray(value)) return []
	return value.flatMap((item) => {
		if (!isRecord(item)) return []
		const action = readString(item, 'action')
		const title = readString(item, 'title')
		if (!action || !title) return []
		return [
			{
				action,
				title,
				icon_url: readNullableString(item, 'icon_url'),
			},
		]
	})
}

async function hasVisibleWindowClient(): Promise<boolean> {
	const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
	return clients.some((client) => isWindowClient(client) && client.visibilityState === 'visible')
}

async function openNotificationTarget(notification: Notification): Promise<void> {
	const actionUrl = notificationActionUrl(notification)
	const targetUrl = new URL(actionUrl || '/', self.location.origin).href
	const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })

	for (const client of clients) {
		if (!isWindowClient(client)) continue
		if (new URL(client.url).origin !== self.location.origin) continue
		if (client.url !== targetUrl) await client.navigate(targetUrl)
		await client.focus()
		return
	}

	await self.clients.openWindow(targetUrl)
}

function isWindowClient(client: Client): client is WindowClient {
	return 'focus' in client && 'visibilityState' in client && 'navigate' in client
}

function notificationActionUrl(notification: Notification): string | null {
	const data = notification.data
	if (!isRecord(data)) return null
	return readNullableString(data, 'action_url')
}

/** cache-first: return cached response, falling back to network (and caching). */
async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
	const cached = await caches.match(request)
	if (cached) return cached

	try {
		const response = await fetch(request)
		if (response.ok) {
			const cache = await caches.open(cacheName)
			cache.put(request, response.clone())
		}
		return response
	} catch {
		return offlineFallback()
	}
}

/** network-first: try network, cache the response, fall back to cache if offline. */
async function networkFirst(request: Request): Promise<Response> {
	const cache = await caches.open(RUNTIME)

	try {
		const response = await fetch(request)
		if (response.ok) {
			cache.put(request, response.clone())
			evictOldEntries(cache)
		}
		return response
	} catch {
		const cached = await cache.match(request)
		if (cached) return cached
		return offlineFallback()
	}
}

/** navigation handler: network-first with offline fallback. */
async function navigationHandler(request: Request): Promise<Response> {
	try {
		const response = await fetch(request)
		return response
	} catch {
		// try the cached SPA fallback page
		const cached = (await caches.match('/200.html')) ?? (await caches.match('/'))
		if (cached) return cached

		return offlineFallback()
	}
}

/** return the offline fallback page. */
async function offlineFallback(): Promise<Response> {
	const cached = await caches.match('/offline.html')
	if (cached) return cached

	return new Response('offline · please check your connection and try again.', {
		status: 503,
		headers: { 'Content-Type': 'text/plain' },
	})
}

/** evict oldest entries when runtime cache exceeds the cap. */
async function evictOldEntries(cache: Cache): Promise<void> {
	const keys = await cache.keys()
	if (keys.length <= RUNTIME_MAX_ENTRIES) return
	const excess = keys.length - RUNTIME_MAX_ENTRIES
	await Promise.all(keys.slice(0, excess).map((key) => cache.delete(key)))
}

// message handler: skip waiting on demand
self.addEventListener('message', (event) => {
	if (event.data?.type === 'SKIP_WAITING') {
		self.skipWaiting()
	}
})
