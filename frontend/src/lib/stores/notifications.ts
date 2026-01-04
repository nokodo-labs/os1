/**
 * Notifications store.
 * Manages notification state, integrates with event stream for real-time updates.
 */

import { derived, get, writable } from 'svelte/store'

import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { v1Client } from '$lib/api/v1/client'
import { getJwtUserId } from '$lib/auth/jwt'
import { getAccessToken } from '$lib/auth/session'

export type Notification = components['schemas']['Notification']
export type Event = components['schemas']['Event']

// event types that generate notifications
const NOTIFICATION_EVENT_TYPES = ['notification.custom', 'notification.agent']

// event types related to threads
const THREAD_EVENT_TYPES = ['thread.created', 'thread.updated', 'thread.deleted']

// all event types related to messages
const MESSAGE_EVENT_TYPES = ['message.created', 'message.updated', 'message.deleted']

// typing indicators
const TYPING_EVENT_TYPES = [
	'typing.user.start',
	'typing.user.stop',
	'typing.agent.start',
	'typing.agent.stop',
]

export const notifications = writable<Notification[]>([])
export const isLoadingNotifications = writable(false)
export const notificationError = writable<string | null>(null)

export const unreadCount = derived(
	notifications,
	($notifications) => $notifications.filter((n) => !n.read_at).length
)

export const unreadNotifications = derived(notifications, ($notifications) =>
	$notifications.filter((n) => !n.read_at)
)

// typing indicators state
export interface TypingIndicator {
	threadId: string
	userId?: string
	agentId?: string
	isAgent: boolean
	startedAt: number
}

export const typingIndicators = writable<TypingIndicator[]>([])

// event handlers registry for components to subscribe
type ThreadEventHandler = (event: StreamMessage) => void
type MessageEventHandler = (event: StreamMessage) => void
type NotificationEventHandler = (event: StreamMessage) => void

const threadEventHandlers = new Set<ThreadEventHandler>()
const messageEventHandlers = new Set<MessageEventHandler>()
const notificationEventHandlers = new Set<NotificationEventHandler>()

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

function handleStreamEvent(message: StreamMessage): void {
	const eventType = message.type

	// handle notification events
	if (NOTIFICATION_EVENT_TYPES.includes(eventType)) {
		// add to local notifications immediately for real-time feel
		const eventData = message as StreamMessage & {
			id: string
			data: Record<string, unknown>
			created_at: string
		}

		type EventScope = 'system' | 'user' | 'thread' | 'message' | 'task' | 'project' | 'file'
		const scopeValue = ((eventData.scope as string) || 'user') as EventScope

		const syntheticNotification: Notification = {
			id: `temp_${Date.now()}`,
			user_id: (eventData.user_id as string) || '',
			event_id: eventData.id,
			dismissed: false,
			read_at: null,
			created_at: eventData.created_at || new Date().toISOString(),
			updated_at: eventData.created_at || new Date().toISOString(),
			event: {
				id: eventData.id,
				type: eventType,
				scope: scopeValue,
				scope_id: (eventData.scope_id as string) || null,
				data: eventData.data || {},
				version: (eventData.version as number) || 1,
				user_id: (eventData.user_id as string) || null,
				thread_id: (eventData.thread_id as string) || null,
				message_id: (eventData.message_id as string) || null,
				task_id: (eventData.task_id as string) || null,
				created_at: eventData.created_at || new Date().toISOString(),
				updated_at: eventData.created_at || new Date().toISOString(),
				expires_at: null,
				metadata_: {},
			},
		}

		notifications.update((list) => [syntheticNotification, ...list])

		// notify handlers
		notificationEventHandlers.forEach((h) => h(message))
	}

	// handle thread events
	if (THREAD_EVENT_TYPES.includes(eventType)) {
		threadEventHandlers.forEach((h) => h(message))
	}

	// handle message events
	if (MESSAGE_EVENT_TYPES.includes(eventType)) {
		messageEventHandlers.forEach((h) => h(message))
	}

	// handle typing indicators
	if (TYPING_EVENT_TYPES.includes(eventType)) {
		const data = message.data as Record<string, unknown> | undefined
		const threadId = (message.thread_id as string) || (data?.thread_id as string) || ''

		if (eventType === 'typing.user.start') {
			const userId = (data?.user_id as string) || ''
			typingIndicators.update((list) => {
				const existing = list.find((t) => t.threadId === threadId && t.userId === userId)
				if (existing) return list
				return [...list, { threadId, userId, isAgent: false, startedAt: Date.now() }]
			})
		} else if (eventType === 'typing.user.stop') {
			const userId = (data?.user_id as string) || ''
			typingIndicators.update((list) =>
				list.filter((t) => !(t.threadId === threadId && t.userId === userId))
			)
		} else if (eventType === 'typing.agent.start') {
			const agentId = (data?.agent_id as string) || ''
			typingIndicators.update((list) => {
				const existing = list.find((t) => t.threadId === threadId && t.agentId === agentId)
				if (existing) return list
				return [...list, { threadId, agentId, isAgent: true, startedAt: Date.now() }]
			})
		} else if (eventType === 'typing.agent.stop') {
			const agentId = (data?.agent_id as string) || ''
			typingIndicators.update((list) =>
				list.filter((t) => !(t.threadId === threadId && t.agentId === agentId))
			)
		}
	}
}

let eventStreamUnsubscribe: (() => void) | null = null

export function initNotifications(): void {
	// subscribe to event stream
	if (!eventStreamUnsubscribe) {
		eventStreamUnsubscribe = eventStreamClient.subscribe(handleStreamEvent)
	}

	// fetch existing notifications
	void refreshNotifications()
}

export function cleanupNotifications(): void {
	if (eventStreamUnsubscribe) {
		eventStreamUnsubscribe()
		eventStreamUnsubscribe = null
	}
	notifications.set([])
	typingIndicators.set([])
}

export async function refreshNotifications(): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		notifications.set([])
		return
	}

	const userId = getJwtUserId(token)
	if (!userId) {
		notifications.set([])
		return
	}

	isLoadingNotifications.set(true)
	notificationError.set(null)

	try {
		const { data, error } = await v1Client().GET('/notifications/users/{user_id}', {
			params: {
				path: { user_id: userId },
				query: { only_unread: false },
			},
		})

		if (error) {
			notificationError.set('failed to load notifications')
			return
		}

		notifications.set(data ?? [])
	} catch {
		notificationError.set('failed to load notifications')
	} finally {
		isLoadingNotifications.set(false)
	}
}

export async function markNotificationRead(notificationId: string): Promise<void> {
	// optimistic update
	notifications.update((list) =>
		list.map((n) => (n.id === notificationId ? { ...n, read_at: new Date().toISOString() } : n))
	)

	try {
		await v1Client().POST('/notifications/{notification_id}/read', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		// revert on error
		await refreshNotifications()
	}
}

export async function dismissNotification(notificationId: string): Promise<void> {
	// optimistic update
	notifications.update((list) =>
		list.map((n) =>
			n.id === notificationId
				? { ...n, dismissed: true, read_at: n.read_at ?? new Date().toISOString() }
				: n
		)
	)

	try {
		await v1Client().POST('/notifications/{notification_id}/dismiss', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		// revert on error
		await refreshNotifications()
	}
}

export async function markAllNotificationsRead(): Promise<void> {
	const token = getAccessToken()
	if (!token) return

	const userId = getJwtUserId(token)
	if (!userId) return

	// optimistic update
	const now = new Date().toISOString()
	notifications.update((list) => list.map((n) => ({ ...n, read_at: n.read_at ?? now })))

	try {
		// TODO: use /notifications/users/{user_id}/read-all when API types are regenerated
		// for now we mark each individually (will be replaced once types are updated)
		const currentNotifications = get(notifications)
		const unread = currentNotifications.filter((n) => !n.read_at)
		await Promise.all(
			unread.slice(0, 10).map((n) =>
				v1Client().POST('/notifications/{notification_id}/read', {
					params: { path: { notification_id: n.id } },
				})
			)
		)
	} catch {
		// revert on error
		await refreshNotifications()
	}
}

export async function deleteNotification(notificationId: string): Promise<void> {
	// use dismiss instead of delete (until API types are regenerated)
	// optimistic update - remove from local list
	notifications.update((list) => list.filter((n) => n.id !== notificationId))

	try {
		await v1Client().POST('/notifications/{notification_id}/dismiss', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		// revert on error
		await refreshNotifications()
	}
}

// helper to get thread typing indicators
export function getThreadTypingIndicators(threadId: string): TypingIndicator[] {
	return get(typingIndicators).filter((t) => t.threadId === threadId)
}
