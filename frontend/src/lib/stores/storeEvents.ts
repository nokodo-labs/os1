import { eventStreamClient, type StreamMessage } from '$lib/api/streaming'

export const STORE_EVENT_TYPES = {
	agents: ['agent.created', 'agent.updated', 'agent.deleted'],
	calendars: ['calendar.created', 'calendar.updated', 'calendar.deleted'],
	calendarEvents: ['calendar.event.created', 'calendar.event.updated', 'calendar.event.deleted'],
	chat: [
		'thread.created',
		'thread.updated',
		'thread.deleted',
		'thread.read',
		'message.created',
		'message.updated',
		'message.deleted',
		'runs.active',
		'run.started',
		'run.error',
		'run.failed',
		'run.completed',
		'task.created',
		'task.updated',
		'task.completed',
		'task.failed',
		'task.cancelled',
	],
	threads: ['thread.created', 'thread.updated', 'thread.deleted'],
	messages: ['message.created', 'message.updated', 'message.deleted'],
	files: ['file.created', 'file.updated', 'file.deleted', 'file.processing', 'file.ready'],
	friends: [
		'friend.request_sent',
		'friend.request_accepted',
		'friend.request_declined',
		'friend.request_cancelled',
		'friend.removed',
	],
	groups: [
		'group.created',
		'group.updated',
		'group.deleted',
		'group.member_added',
		'group.member_removed',
	],
	notes: ['note.created', 'note.updated', 'note.deleted'],
	notifications: [
		'notification.custom',
		'notification.agent',
		'notification.reminder_alert',
		'notification.calendar_event_alert',
	],
	permissions: ['role.updated', 'role.deleted'],
	preferences: ['user.preferences_updated', 'user_client.preferences_updated'],
	projects: ['project.created', 'project.updated', 'project.deleted'],
	projectCounts: [
		'thread.created',
		'thread.updated',
		'thread.deleted',
		'note.created',
		'note.updated',
		'note.deleted',
		'file.created',
		'file.updated',
		'file.deleted',
		'file.processing',
		'file.ready',
		'reminder_list.created',
		'reminder_list.updated',
		'reminder_list.deleted',
		'calendar.created',
		'calendar.updated',
		'calendar.deleted',
	],
	reminders: [
		'reminder.created',
		'reminder.updated',
		'reminder.completed',
		'reminder.deleted',
		'reminder_list.created',
		'reminder_list.updated',
		'reminder_list.deleted',
	],
	resourceAccessGlobal: [
		'group.member_added',
		'group.member_removed',
		'role.updated',
		'role.deleted',
		'settings.updated',
	],
	resourceAccessResource: ['access.updated', 'resource.access.updated'],
	runs: ['runs.active', 'run.started', 'run.completed', 'run.error', 'run.failed'],
	settings: ['settings.updated'],
	typing: ['typing.user.start', 'typing.user.stop'],
} as const

export type StoreEventType = (typeof STORE_EVENT_TYPES)[keyof typeof STORE_EVENT_TYPES][number]
export type StoreEvent<T extends string = StoreEventType> = StreamMessage & { type: T }
export type StoreEventHandler<T extends string = StoreEventType> = (message: StoreEvent<T>) => void

export function subscribeToStoreEvents<T extends readonly string[]>(
	eventTypes: T,
	handler: StoreEventHandler<T[number]>
): () => void {
	return eventStreamClient.subscribeTypes(eventTypes, (message) => {
		handler(message as StoreEvent<T[number]>)
	})
}

export function subscribeToStoreEventPrefixes(
	prefixes: readonly string[],
	handler: StoreEventHandler<string>
): () => void {
	return eventStreamClient.subscribePrefixes(prefixes, (message) => {
		handler(message as StoreEvent<string>)
	})
}

export function storeEventData(message: StreamMessage): Record<string, unknown> | null {
	const data = message.data
	if (data && typeof data === 'object' && !Array.isArray(data)) {
		return data as Record<string, unknown>
	}
	return null
}

export function storeEventPayload(message: StreamMessage): Record<string, unknown> {
	return storeEventData(message) ?? message
}

export function storeEventString(message: StreamMessage, keys: readonly string[]): string | null {
	const payloads = [storeEventData(message), message].filter(Boolean) as Record<string, unknown>[]
	for (const data of payloads) {
		for (const key of keys) {
			const value = data[key]
			if (typeof value === 'string' && value.length > 0) return value
		}
	}
	return null
}

export function isStoreEventType(message: StreamMessage, eventTypes: readonly string[]): boolean {
	return eventTypes.includes(message.type)
}
