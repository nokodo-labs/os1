/**
 * Notifications store.
 * Manages notification state, integrates with event stream for real-time updates.
 */

import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { v1Client } from '$lib/api/v1/client'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken } from '$lib/auth/session'
import { SvelteDate, SvelteSet } from 'svelte/reactivity'

export type Notification = components['schemas']['Notification']
export type Event = components['schemas']['Event']

const NOTIFICATION_EVENT_TYPES = ['notification.custom', 'notification.agent']
const THREAD_EVENT_TYPES = ['thread.created', 'thread.updated', 'thread.deleted']
const MESSAGE_EVENT_TYPES = ['message.created', 'message.updated', 'message.deleted']
const TYPING_EVENT_TYPES = [
	'typing.user.start',
	'typing.user.stop',
	'typing.agent.start',
	'typing.agent.stop',
]

export interface TypingIndicator {
	threadId: string
	userId?: string
	agentId?: string
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

	readonly unreadCount = $derived(this.list.filter((n) => !n.read_at).length)
	readonly unread = $derived(this.list.filter((n) => !n.read_at))

	#refreshTimer: ReturnType<typeof setTimeout> | null = null
	#unsubscribe: (() => void) | null = null

	#scheduleRefresh = () => {
		if (this.#refreshTimer) clearTimeout(this.#refreshTimer)
		this.#refreshTimer = setTimeout(() => {
			this.#refreshTimer = null
			void this.refresh()
		}, 350)
	}

	#handleStreamEvent = (message: StreamMessage) => {
		const eventType = message.type

		if (NOTIFICATION_EVENT_TYPES.includes(eventType)) {
			this.#scheduleRefresh()
			for (const handler of notificationEventHandlers) handler(message)
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
			} else if (eventType === 'typing.agent.start') {
				const agentId = (data?.agent_id as string) || ''
				if (
					!this.typingIndicators.find(
						(t) => t.threadId === threadId && t.agentId === agentId
					)
				) {
					this.typingIndicators = [
						...this.typingIndicators,
						{ threadId, agentId, isAgent: true, startedAt: Date.now() },
					]
				}
			} else if (eventType === 'typing.agent.stop') {
				const agentId = (data?.agent_id as string) || ''
				this.typingIndicators = this.typingIndicators.filter(
					(t) => !(t.threadId === threadId && t.agentId === agentId)
				)
			}
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
			const { data, error } = await v1Client().GET('/notifications/users/{user_id}', {
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
			await v1Client().POST('/notifications/{notification_id}/read', {
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
			await v1Client().POST('/notifications/{notification_id}/dismiss', {
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
					v1Client().POST('/notifications/{notification_id}/read', {
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
			await v1Client().POST('/notifications/{notification_id}/dismiss', {
				params: { path: { notification_id: notificationId } },
			})
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
