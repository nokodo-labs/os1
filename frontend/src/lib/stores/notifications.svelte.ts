/**
 * Notifications store.
 * Manages notification state, integrates with event stream for real-time updates.
 */

import { api } from '$lib/api/client'
import type { StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken } from '$lib/auth/session.svelte'
import {
	STORE_EVENT_TYPES,
	storeEventData,
	storeEventString,
	subscribeToStoreEvents,
} from '$lib/stores/storeEvents'
import { SvelteDate, SvelteSet } from 'svelte/reactivity'

export type Notification = components['schemas']['Notification']
export type Event = components['schemas']['Event']

export type EphemeralVariant = 'error' | 'success' | 'info' | 'warning'

export interface ToastItem {
	/** unique UI handle for this toast */
	id: string
	type: 'notification' | 'ephemeral'
	/** only set when type === 'ephemeral' */
	variant?: EphemeralVariant
	/** only set when type === 'notification' - the backing event_id */
	eventId?: string
	title: string
	body: string
	iconUrl?: string | null
	imageUrl?: string | null
	addedAt: number
}

const NOTIFICATION_EVENT_TYPES = STORE_EVENT_TYPES.notifications
const THREAD_EVENT_TYPES = STORE_EVENT_TYPES.threads
const MESSAGE_EVENT_TYPES = STORE_EVENT_TYPES.messages
const TYPING_EVENT_TYPES = STORE_EVENT_TYPES.typing
const RUN_EVENT_TYPES = STORE_EVENT_TYPES.runs
const FRIEND_EVENT_TYPES = STORE_EVENT_TYPES.friends
const NOTIFICATIONS_SUBSCRIPTION_TYPES = [
	...NOTIFICATION_EVENT_TYPES,
	...THREAD_EVENT_TYPES,
	...MESSAGE_EVENT_TYPES,
	...TYPING_EVENT_TYPES,
	...RUN_EVENT_TYPES,
	...FRIEND_EVENT_TYPES,
] as const
const NOTIFICATION_EVENT_TYPE_SET = new Set<string>(NOTIFICATION_EVENT_TYPES)
const THREAD_EVENT_TYPE_SET = new Set<string>(THREAD_EVENT_TYPES)
const MESSAGE_EVENT_TYPE_SET = new Set<string>(MESSAGE_EVENT_TYPES)
const TYPING_EVENT_TYPE_SET = new Set<string>(TYPING_EVENT_TYPES)
const RUN_EVENT_TYPE_SET = new Set<string>(RUN_EVENT_TYPES)
const FRIEND_EVENT_TYPE_SET = new Set<string>(FRIEND_EVENT_TYPES)

const FRIEND_TOAST_TYPES = ['friend.request_sent', 'friend.request_accepted']

export interface TypingIndicator {
	threadId: string
	userId?: string
	isAgent: boolean
	startedAt: number
}

type ThreadEventHandler = (event: StreamMessage) => void
type MessageEventHandler = (event: StreamMessage) => void
type NotificationEventHandler = (event: StreamMessage) => void

const threadEventHandlers = new SvelteSet<ThreadEventHandler>()
const messageEventHandlers = new SvelteSet<MessageEventHandler>()
const notificationEventHandlers = new SvelteSet<NotificationEventHandler>()

class NotificationsStore {
	list = $state<Notification[]>([])
	isLoading = $state(false)
	error = $state<string | null>(null)
	typingIndicators = $state<TypingIndicator[]>([])
	toasts = $state<ToastItem[]>([])

	readonly unreadCount = $derived(this.list.filter((n) => !n.read_at).length)
	readonly unread = $derived(this.list.filter((n) => !n.read_at))

	#refreshTimer: ReturnType<typeof setTimeout> | null = null
	#unsubscribe: (() => void) | null = null
	#stale = $state(true)
	readonly stale = $derived(this.#stale)
	static readonly TOAST_DURATION_MS = 12000

	get initialized(): boolean {
		return this.#unsubscribe !== null
	}

	#scheduleRefresh = () => {
		if (this.#refreshTimer) clearTimeout(this.#refreshTimer)
		this.#refreshTimer = setTimeout(() => {
			this.#refreshTimer = null
			void this.refresh()
		}, 350)
	}

	#pushToast = (message: StreamMessage) => {
		const data = storeEventData(message)
		const title = (data?.title as string) || message.type || 'notification'
		const body = (data?.body as string) || ''
		const iconUrl = (data?.icon_url as string) || null
		const imageUrl = (data?.image_url as string) || null
		const eventId = typeof message.id === 'string' ? message.id : null
		if (!eventId) return

		const id = crypto.randomUUID()
		this.toasts = [
			...this.toasts,
			{
				id,
				type: 'notification',
				eventId,
				title,
				body,
				iconUrl,
				imageUrl,
				addedAt: Date.now(),
			},
		]
	}

	#pushFriendToast = (message: StreamMessage) => {
		const eventId = typeof message.id === 'string' ? message.id : null
		if (!eventId) return
		const labels: Record<string, string> = {
			'friend.request_sent': 'new friend request',
			'friend.request_accepted': 'friend request accepted',
		}
		const title = labels[message.type] ?? 'friend update'
		const id = crypto.randomUUID()
		this.toasts = [
			...this.toasts,
			{
				id,
				type: 'notification',
				eventId,
				title,
				body: '',
				iconUrl: null,
				imageUrl: null,
				addedAt: Date.now(),
			},
		]
	}

	dismissToast = (id: string) => {
		this.toasts = this.toasts.filter((t) => t.id !== id)
	}

	/** push an ephemeral (non-notification-backed) toast. */
	pushEphemeralToast = (variant: EphemeralVariant, message: string): string => {
		const id = `ephemeral-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
		this.toasts = [
			...this.toasts,
			{
				id,
				type: 'ephemeral',
				variant,
				title: message,
				body: '',
				iconUrl: null,
				imageUrl: null,
				addedAt: Date.now(),
			},
		]
		return id
	}

	#handleStreamEvent = (message: StreamMessage) => {
		const eventType = message.type

		if (NOTIFICATION_EVENT_TYPE_SET.has(eventType)) {
			this.#scheduleRefresh()
			this.#pushToast(message)
			for (const handler of notificationEventHandlers) handler(message)
		}

		if (FRIEND_EVENT_TYPE_SET.has(eventType)) {
			if (FRIEND_TOAST_TYPES.includes(eventType)) {
				this.#pushFriendToast(message)
			}
		}

		if (THREAD_EVENT_TYPE_SET.has(eventType)) {
			for (const handler of threadEventHandlers) handler(message)
		}

		if (MESSAGE_EVENT_TYPE_SET.has(eventType)) {
			for (const handler of messageEventHandlers) handler(message)
		}

		if (TYPING_EVENT_TYPE_SET.has(eventType)) {
			const data = storeEventData(message)
			const threadId = storeEventString(message, ['thread_id']) ?? ''

			if (eventType === 'typing.user.start') {
				const userId = (data?.user_id as string) || ''
				if (
					!this.typingIndicators.find(
						(t) => t.threadId === threadId && t.userId === userId
					)
				) {
					this.typingIndicators = [
						...this.typingIndicators,
						{ threadId, userId, isAgent: false, startedAt: Date.now() },
					]
				}
			} else if (eventType === 'typing.user.stop') {
				const userId = (data?.user_id as string) || ''
				this.typingIndicators = this.typingIndicators.filter(
					(t) => !(t.threadId === threadId && t.userId === userId)
				)
			}
		}

		// run events are forwarded via the generic stream - no further handling here
		if (RUN_EVENT_TYPE_SET.has(eventType)) {
			// no-op: handled by activeRunsStore
		}
	}

	init = () => {
		if (this.#unsubscribe) return
		this.#unsubscribe = subscribeToStoreEvents(
			NOTIFICATIONS_SUBSCRIPTION_TYPES,
			this.#handleStreamEvent
		)
		void this.refresh()
	}

	cleanup = () => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
		this.clear()
	}

	invalidate = (): void => {
		this.#stale = true
	}

	clear = (): void => {
		if (this.#refreshTimer) clearTimeout(this.#refreshTimer)
		this.#refreshTimer = null
		this.list = []
		this.typingIndicators = []
		this.isLoading = false
		this.error = null
		this.#stale = true
	}

	refresh = async (): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.list = []
			this.#stale = true
			return
		}

		const userId = getJwtUserId(token)
		if (!userId) {
			this.list = []
			this.#stale = true
			return
		}

		this.isLoading = true
		this.error = null

		try {
			const { data, error } = await api.GET('/v1/notifications/users/{user_id}', {
				params: {
					path: { user_id: userId },
					query: { only_unread: false },
				},
			})

			if (error) {
				this.error = 'failed to load notifications'
				this.#stale = true
				return
			}

			this.list = data ?? []
			this.#stale = false
		} catch {
			this.error = 'failed to load notifications'
			this.#stale = true
		} finally {
			this.isLoading = false
		}
	}

	markRead = async (notificationId: string): Promise<void> => {
		this.list = this.list.map((n) =>
			n.id === notificationId ? { ...n, read_at: new SvelteDate().toISOString() } : n
		)

		try {
			await api.POST('/v1/notifications/{notification_id}/read', {
				params: { path: { notification_id: notificationId } },
			})
		} catch {
			await this.refresh()
		}
	}

	dismiss = async (notificationId: string): Promise<void> => {
		this.list = this.list.map((n) =>
			n.id === notificationId
				? { ...n, dismissed: true, read_at: n.read_at ?? new SvelteDate().toISOString() }
				: n
		)

		try {
			await api.POST('/v1/notifications/{notification_id}/dismiss', {
				params: { path: { notification_id: notificationId } },
			})
		} catch {
			await this.refresh()
		}
	}

	markAllRead = async (): Promise<void> => {
		const token = getAccessToken()
		if (!token) return

		const userId = getJwtUserId(token)
		if (!userId) return

		const unread = this.list.filter((n) => !n.read_at)
		const now = new SvelteDate().toISOString()
		this.list = this.list.map((n) => ({ ...n, read_at: n.read_at ?? now }))

		try {
			await Promise.all(
				unread.map((n) =>
					api.POST('/v1/notifications/{notification_id}/read', {
						params: { path: { notification_id: n.id } },
					})
				)
			)
		} catch {
			await this.refresh()
		}
	}

	delete = async (notificationId: string): Promise<void> => {
		this.list = this.list.filter((n) => n.id !== notificationId)

		try {
			await api.POST('/v1/notifications/{notification_id}/dismiss', {
				params: { path: { notification_id: notificationId } },
			})
		} catch {
			await this.refresh()
		}
	}

	dismissAll = async (): Promise<void> => {
		const ids = this.list.map((n) => n.id)
		this.list = []

		try {
			await Promise.all(
				ids.map((id) =>
					api.POST('/v1/notifications/{notification_id}/dismiss', {
						params: { path: { notification_id: id } },
					})
				)
			)
		} catch {
			await this.refresh()
		}
	}

	getThreadTyping = (threadId: string): TypingIndicator[] => {
		return this.typingIndicators.filter((t) => t.threadId === threadId)
	}
}

export const notifications = new NotificationsStore()

export function onThreadEvent(handler: ThreadEventHandler): () => void {
	threadEventHandlers.add(handler)
	return () => threadEventHandlers.delete(handler)
}

export function onMessageEvent(handler: MessageEventHandler): () => void {
	messageEventHandlers.add(handler)
	return () => messageEventHandlers.delete(handler)
}

export function onNotificationEvent(handler: NotificationEventHandler): () => void {
	notificationEventHandlers.add(handler)
	return () => notificationEventHandlers.delete(handler)
}

/** display a transient ephemeral error toast. */
export function showError(message: string): string {
	return notifications.pushEphemeralToast('error', message)
}
