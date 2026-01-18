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

export let notifications = $state<Notification[]>([])
export let isLoadingNotifications = $state(false)
export let notificationError = $state<string | null>(null)

export const unreadCount = $derived.by(() => notifications.filter((n) => !n.read_at).length)

export const unreadNotifications = $derived.by(() => notifications.filter((n) => !n.read_at))

export interface TypingIndicator {
	threadId: string
	userId?: string
	agentId?: string
	isAgent: boolean
	startedAt: number
}

export let typingIndicators = $state<TypingIndicator[]>([])

type ThreadEventHandler = (event: StreamMessage) => void
type MessageEventHandler = (event: StreamMessage) => void
type NotificationEventHandler = (event: StreamMessage) => void

const threadEventHandlers = new SvelteSet<ThreadEventHandler>()
const messageEventHandlers = new SvelteSet<MessageEventHandler>()
const notificationEventHandlers = new SvelteSet<NotificationEventHandler>()

let refreshTimer: ReturnType<typeof setTimeout> | null = null

function scheduleNotificationsRefresh(): void {
	if (refreshTimer) clearTimeout(refreshTimer)
	refreshTimer = setTimeout(() => {
		refreshTimer = null
		void refreshNotifications()
	}, 350)
}

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

	if (NOTIFICATION_EVENT_TYPES.includes(eventType)) {
		scheduleNotificationsRefresh()
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
			typingIndicators = (() => {
				const list = typingIndicators
				const existing = list.find((t) => t.threadId === threadId && t.userId === userId)
				if (existing) return list
				return [...list, { threadId, userId, isAgent: false, startedAt: Date.now() }]
			})()
		} else if (eventType === 'typing.user.stop') {
			const userId = (data?.user_id as string) || ''
			typingIndicators = typingIndicators.filter(
				(t) => !(t.threadId === threadId && t.userId === userId)
			)
		} else if (eventType === 'typing.agent.start') {
			const agentId = (data?.agent_id as string) || ''
			typingIndicators = (() => {
				const list = typingIndicators
				const existing = list.find((t) => t.threadId === threadId && t.agentId === agentId)
				if (existing) return list
				return [...list, { threadId, agentId, isAgent: true, startedAt: Date.now() }]
			})()
		} else if (eventType === 'typing.agent.stop') {
			const agentId = (data?.agent_id as string) || ''
			typingIndicators = typingIndicators.filter(
				(t) => !(t.threadId === threadId && t.agentId === agentId)
			)
		}
	}
}

let eventStreamUnsubscribe: (() => void) | null = null

export function initNotifications(): void {
	if (!eventStreamUnsubscribe) {
		eventStreamUnsubscribe = eventStreamClient.subscribe(handleStreamEvent)
	}
	void refreshNotifications()
}

export function cleanupNotifications(): void {
	if (eventStreamUnsubscribe) {
		eventStreamUnsubscribe()
		eventStreamUnsubscribe = null
	}
	notifications = []
	typingIndicators = []
}

export async function refreshNotifications(): Promise<void> {
	const token = getAccessToken()
	if (!token) {
		notifications = []
		return
	}

	const userId = getJwtUserId(token)
	if (!userId) {
		notifications = []
		return
	}

	isLoadingNotifications = true
	notificationError = null

	try {
		const { data, error } = await v1Client().GET('/notifications/users/{user_id}', {
			params: {
				path: { user_id: userId },
				query: { only_unread: false },
			},
		})

		if (error) {
			notificationError = 'failed to load notifications'
			return
		}

		notifications = data ?? []
	} catch {
		notificationError = 'failed to load notifications'
	} finally {
		isLoadingNotifications = false
	}
}

export async function markNotificationRead(notificationId: string): Promise<void> {
	notifications = notifications.map((n) =>
		n.id === notificationId ? { ...n, read_at: new SvelteDate().toISOString() } : n
	)

	try {
		await v1Client().POST('/notifications/{notification_id}/read', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		await refreshNotifications()
	}
}

export async function dismissNotification(notificationId: string): Promise<void> {
	notifications = notifications.map((n) =>
		n.id === notificationId
			? {
					...n,
					dismissed: true,
					read_at: n.read_at ?? new SvelteDate().toISOString(),
				}
			: n
	)

	try {
		await v1Client().POST('/notifications/{notification_id}/dismiss', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		await refreshNotifications()
	}
}

export async function markAllNotificationsRead(): Promise<void> {
	const token = getAccessToken()
	if (!token) return

	const userId = getJwtUserId(token)
	if (!userId) return

	const now = new SvelteDate().toISOString()
	notifications = notifications.map((n) => ({ ...n, read_at: n.read_at ?? now }))

	try {
		const currentNotifications = notifications
		const unread = currentNotifications.filter((n) => !n.read_at)
		await Promise.all(
			unread.slice(0, 10).map((n) =>
				v1Client().POST('/notifications/{notification_id}/read', {
					params: { path: { notification_id: n.id } },
				})
			)
		)
	} catch {
		await refreshNotifications()
	}
}

export async function deleteNotification(notificationId: string): Promise<void> {
	notifications = notifications.filter((n) => n.id !== notificationId)

	try {
		await v1Client().POST('/notifications/{notification_id}/dismiss', {
			params: { path: { notification_id: notificationId } },
		})
	} catch {
		await refreshNotifications()
	}
}

export function getThreadTypingIndicators(threadId: string): TypingIndicator[] {
	return typingIndicators.filter((t) => t.threadId === threadId)
}
