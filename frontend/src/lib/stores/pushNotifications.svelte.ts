import { browser } from '$app/environment'
import { api } from '$lib/api/client'
import type { components } from '$lib/api/types'
import { preferences } from '$lib/stores/preferences.svelte'
import { session } from '$lib/stores/session.svelte'
import { settingsState } from '$lib/stores/settings.svelte'
import { ensureUserClient } from '$lib/stores/userClient.svelte'

type NotificationPushSubscriptionCreate =
	components['schemas']['NotificationPushSubscriptionCreate']

type PushPermissionState = NotificationPermission | 'unsupported'

type PushStatus =
	| 'idle'
	| 'disabled'
	| 'unsupported'
	| 'not_configured'
	| 'prompting'
	| 'subscribing'
	| 'ready'
	| 'blocked'
	| 'failed'

export const pushNotifications = $state({
	supported: false,
	permission: 'unsupported' as PushPermissionState,
	status: 'idle' as PushStatus,
	error: null as string | null,
	subscriptionEndpoint: null as string | null,
	serverConfigured: false,
})

let didInit = false
let cleanup: (() => void) | null = null
let requestedForUserId: string | null = null
let setupInFlight: Promise<boolean> | null = null
let disableInFlight: Promise<void> | null = null

/** return whether this browser can request app notification permission. */
function canUsePushNotifications(): boolean {
	return (
		browser &&
		window.isSecureContext &&
		'Notification' in window &&
		'serviceWorker' in navigator &&
		'PushManager' in window
	)
}

/** sync the reactive state with the current browser permission. */
function refreshPermissionState(): void {
	pushNotifications.supported = canUsePushNotifications()
	pushNotifications.permission = pushNotifications.supported
		? Notification.permission
		: 'unsupported'
	pushNotifications.serverConfigured = Boolean(getVapidPublicKey())

	if (!pushNotifications.supported) {
		pushNotifications.status = 'unsupported'
		return
	}
	if (pushNotifications.permission === 'denied') {
		pushNotifications.status = 'blocked'
		return
	}
	if (!pushNotifications.serverConfigured) {
		pushNotifications.status = 'not_configured'
	}
}

function getVapidPublicKey(): string | null {
	const notificationSettings = settingsState.data?.notifications
	if (!notificationSettings?.web_push_enabled) return null
	return notificationSettings.vapid_public_key || null
}

function urlBase64ToArrayBuffer(value: string): ArrayBuffer {
	const padding = '='.repeat((4 - (value.length % 4)) % 4)
	const base64 = `${value}${padding}`.replace(/-/g, '+').replace(/_/g, '/')
	const rawData = window.atob(base64)
	const buffer = new ArrayBuffer(rawData.length)
	const output = new Uint8Array(buffer)
	for (let index = 0; index < rawData.length; index += 1) {
		output[index] = rawData.charCodeAt(index)
	}
	return buffer
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
	const bytes = new Uint8Array(buffer)
	let binary = ''
	for (const byte of bytes) binary += String.fromCharCode(byte)
	return window.btoa(binary)
}

async function unregisterBrowserSubscription(): Promise<void> {
	if (!canUsePushNotifications()) return
	const registration = await navigator.serviceWorker.ready
	const subscription = await registration.pushManager.getSubscription()
	if (!subscription) {
		pushNotifications.subscriptionEndpoint = null
		return
	}
	const userId = session.currentUserId
	const currentClient = userId ? await ensureUserClient() : null

	if (userId && currentClient) {
		await api
			.DELETE('/v1/users/{user_id}/clients/{client_id}/push-subscriptions', {
				params: { path: { user_id: userId, client_id: currentClient.id } },
				body: { endpoint: subscription.endpoint },
			})
			.catch(() => {})
	}
	await subscription.unsubscribe().catch(() => false)
	pushNotifications.subscriptionEndpoint = null
}

async function registerBrowserSubscription(subscription: PushSubscription): Promise<boolean> {
	const currentClient = await ensureUserClient()
	if (!currentClient) {
		pushNotifications.status = 'failed'
		pushNotifications.error = 'could not register this client'
		return false
	}

	const p256dh = subscription.getKey('p256dh')
	const auth = subscription.getKey('auth')
	if (!p256dh || !auth) {
		pushNotifications.status = 'failed'
		pushNotifications.error = 'browser did not provide push keys'
		return false
	}

	const body: NotificationPushSubscriptionCreate = {
		endpoint: subscription.endpoint,
		keys: {
			p256dh: arrayBufferToBase64(p256dh),
			auth: arrayBufferToBase64(auth),
		},
		expires_at: subscription.expirationTime
			? new Date(subscription.expirationTime).toISOString()
			: null,
	}
	const { data, error, response } = await api.POST(
		'/v1/users/{user_id}/clients/{client_id}/push-subscriptions',
		{
			params: { path: { user_id: currentClient.user_id, client_id: currentClient.id } },
			body,
		}
	)
	if (error || !response.ok || !data) {
		pushNotifications.status = 'failed'
		pushNotifications.error = 'could not register push notifications'
		return false
	}

	pushNotifications.subscriptionEndpoint = data.endpoint
	pushNotifications.status = 'ready'
	pushNotifications.error = null
	return true
}

async function ensureBrowserSubscription(requestPermission: boolean): Promise<boolean> {
	refreshPermissionState()

	if (!preferences.data.notifications.pushEnabled) {
		pushNotifications.status = 'disabled'
		return false
	}
	if (!pushNotifications.supported) return false
	const vapidPublicKey = getVapidPublicKey()
	if (!vapidPublicKey) {
		pushNotifications.status = 'not_configured'
		return false
	}
	if (pushNotifications.permission === 'denied') {
		pushNotifications.status = 'blocked'
		return false
	}
	if (pushNotifications.permission !== 'granted') {
		if (!requestPermission) return false
		pushNotifications.status = 'prompting'
		const permission = await Notification.requestPermission()
		pushNotifications.permission = permission
		if (permission !== 'granted') {
			pushNotifications.status = permission === 'denied' ? 'blocked' : 'idle'
			return false
		}
	}

	pushNotifications.status = 'subscribing'
	pushNotifications.error = null
	const registration = await navigator.serviceWorker.ready
	const existing = await registration.pushManager.getSubscription()
	const subscription =
		existing ??
		(await registration.pushManager.subscribe({
			userVisibleOnly: true,
			applicationServerKey: urlBase64ToArrayBuffer(vapidPublicKey),
		}))

	return await registerBrowserSubscription(subscription)
}

/** request browser permission and register push delivery when allowed. */
export async function requestPushNotifications(): Promise<boolean> {
	if (!browser) return false
	if (setupInFlight) return setupInFlight
	setupInFlight = ensureBrowserSubscription(true)
		.catch((error: unknown) => {
			pushNotifications.status = 'failed'
			pushNotifications.error =
				error instanceof Error ? error.message : 'notification setup failed'
			return false
		})
		.finally(() => {
			setupInFlight = null
		})
	return setupInFlight
}

/** unregister this browser subscription when the user disables push. */
export async function disablePushNotifications(): Promise<void> {
	if (!browser) return
	if (disableInFlight) return disableInFlight
	disableInFlight = unregisterBrowserSubscription()
		.catch((error: unknown) => {
			pushNotifications.error =
				error instanceof Error ? error.message : 'notification cleanup failed'
		})
		.finally(() => {
			pushNotifications.status = 'disabled'
			disableInFlight = null
		})
	return disableInFlight
}

/** start watching session preferences and prompt on boot when enabled. */
export function initPushNotifications(): void {
	if (!browser || didInit) return
	didInit = true
	refreshPermissionState()

	const cleanupEffect = $effect.root(() => {
		$effect(() => {
			const userId = session.currentUserId
			const enabled = preferences.data.notifications.pushEnabled
			const configured = Boolean(getVapidPublicKey())

			if (!userId || !enabled) {
				requestedForUserId = null
				if (!enabled) void disablePushNotifications()
				else pushNotifications.status = 'disabled'
				return
			}

			if (!configured) {
				requestedForUserId = null
				refreshPermissionState()
				return
			}

			if (requestedForUserId === userId) return
			requestedForUserId = userId
			void requestPushNotifications()
		})
	})

	cleanup = () => {
		cleanupEffect()
	}

	if (import.meta.hot) {
		import.meta.hot.dispose(() => destroyPushNotifications())
	}
}

/** stop watching push notification preferences. */
export function destroyPushNotifications(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	requestedForUserId = null
	setupInFlight = null
	disableInFlight = null
	pushNotifications.error = null
	refreshPermissionState()
}
