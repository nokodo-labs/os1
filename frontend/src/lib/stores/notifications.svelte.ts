/**
 * Notifications store.
 * Manages notification state, integrates with event stream for real-time updates.
 */

import { apiClient } from '$lib/api/client'
import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken } from '$lib/auth/session.svelte'
import { SvelteDate, SvelteSet } from 'svelte/reactivity'

export type Notification = components['schemas']['Notification']
export type Event = components['schemas']['Event']

export interface ToastItem {
	id: string
	title: string
	body: string
	iconUrl?: string | null
	imageUrl?: string | null
	addedAt: number
}

const NOTIFICATION_EVENT_TYPES = ['notification.custom', 'notification.agent']
const THREAD_EVENT_TYPES = ['thread.created', 'thread.updated', 'thread.deleted']
const MESSAGE_EVENT_TYPES = ['message.created', 'message.updated', 'message.deleted']
const TYPING_EVENT_TYPES = ['typing.user.start', 'typing.user.stop']
const RUN_EVENT_TYPES = ['run.started', 'run.completed', 'runs.active']
const FRIEND_EVENT_TYPES = [
	'friend.request_sent',
	'friend.request_accepted',
	'friend.request_declined',
	'friend.removed',
]

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
	static readonly TOAST_DURATION_MS = 12000

	#scheduleRefresh = () => {
		if (this.#refreshTimer) clearTimeout(this.#refreshTimer)
		this.#refreshTimer = setTimeout(() => {
			this.#refreshTimer = null
			void this.refresh()
		}, 350)
	}

	#pushToast = (message: StreamMessage) => {
		const data = message.data as Record<string, unknown> | undefined
		const title = (data?.title as string) || message.type || 'notification'
		const body = (data?.body as string) || ''
		const iconUrl = (data?.icon_url as string) || null
		const imageUrl = (data?.image_url as string) || null
		const id = typeof message.id === 'string' ? message.id : null
		if (!id) return

		this.toasts = [...this.toasts, { id, title, body, iconUrl, imageUrl, addedAt: Date.now() }]
	}

	#pushFriendToast = (message: StreamMessage) => {
		const id = typeof message.id === 'string' ? message.id : null
		if (!id) return
		const labels: Record<string, string> = {
			'friend.request_sent': 'new friend request',
			'friend.request_accepted': 'friend request accepted',
		}
		const title = labels[message.type] ?? 'friend update'
		this.toasts = [
			...this.toasts,
			{ id, title, body: '', iconUrl: null, imageUrl: null, addedAt: Date.now() },
		]
	}

	dismissToast = (id: string) => {
		this.toasts = this.toasts.filter((t) => t.id !== id)
	}

	#handleStreamEvent = (message: StreamMessage) => {
		const eventType = message.type

		if (NOTIFICATION_EVENT_TYPES.includes(eventType)) {
			this.#scheduleRefresh()
			this.#pushToast(message)
			for (const handler of notificationEventHandlers) handler(message)
		}

		if (FRIEND_EVENT_TYPES.includes(eventType)) {
			if (FRIEND_TOAST_TYPES.includes(eventType)) {
				this.#pushFriendToast(message)
			}
		}

		if (THREAD_EVENT_TYPES.includes(eventType)) {
			for (const handler of threadEventHandlers) handler(message)
		}

		if (MESSAGE_EVENT_TYPES.includes(eventType)) {
			for (const handler of messageEventHandlers) handler(message)
		}

		if (TYPING_EVENT_TYPES.includes(eventType)) {
			const data = message.data as Record<string, unknown> | undefined
			const threadId = (message.thread_id as string) || (data?.thread_id as string) || ''

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
		if (RUN_EVENT_TYPES.includes(eventType)) {
			// no-op: handled by chat.svelte.ts subscribeToAgentRunEvents
		}
	}

	init = () => {
		if (!this.#unsubscribe) {
			this.#unsubscribe = eventStreamClient.subscribe(this.#handleStreamEvent)
		}
		void this.refresh()
	}

	cleanup = () => {
		this.#unsubscribe?.()
		this.#unsubscribe = null
		this.list = []
		this.typingIndicators = []
	}

	refresh = async (): Promise<void> => {
		const token = getAccessToken()
		if (!token) {
			this.list = []
			return
		}

		const userId = getJwtUserId(token)
		if (!userId) {
			this.list = []
			return
		}

		this.isLoading = true
		this.error = null

		try {
			const { data, error } = await apiClient().GET('/v1/notifications/users/{user_id}', {
				params: {
					path: { user_id: userId },
					query: { only_unread: false },
				},
			})

			if (error) {
				this.error = 'failed to load notifications'
				return
			}

			this.list = data ?? []
		} catch {
			this.error = 'failed to load notifications'
		} finally {
			this.isLoading = false
		}
	}

	markRead = async (notificationId: string): Promise<void> => {
		this.list = this.list.map((n) =>
			n.id === notificationId ? { ...n, read_at: new SvelteDate().toISOString() } : n
		)

		try {
			await apiClient().POST('/v1/notifications/{notification_id}/read', {
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
			await apiClient().POST('/v1/notifications/{notification_id}/dismiss', {
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
				unread.slice(0, 10).map((n) =>
					apiClient().POST('/v1/notifications/{notification_id}/read', {
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
			await apiClient().POST('/v1/notifications/{notification_id}/dismiss', {
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
				ids.slice(0, 20).map((id) =>
					apiClient().POST('/v1/notifications/{notification_id}/dismiss', {
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
