import {
	genericNotificationAccent,
	genericNotificationIcon,
	notificationAccent,
	notificationAppId,
	notificationIcon,
} from '$lib/resources/notificationVisuals'
import { accentColors } from '$lib/contexts/themeContext.svelte'
import { appVisuals, type AppVisualId } from '$lib/resources/resourceVisuals'
import { describe, expect, it } from 'vitest'

function appIcon(id: AppVisualId) {
	return appVisuals.find((app) => app.id === id)?.icon
}

function appAccent(id: AppVisualId) {
	return appVisuals.find((app) => app.id === id)?.accent
}

/** every event type the backend can back a notification with, and its owning app. */
const appByEventType: [string, AppVisualId][] = [
	['notification.reminder_alert', 'reminders'],
	['notification.calendar_event_alert', 'calendar'],
	['notification.agent', 'messages'],
	['reminder.created', 'reminders'],
	['reminder.completed', 'reminders'],
	['reminder_list.updated', 'reminders'],
	['calendar.created', 'calendar'],
	['calendar.event.updated', 'calendar'],
	['note.created', 'notes'],
	['file.ready', 'library'],
	['project.updated', 'projects'],
	['thread.created', 'messages'],
	['message.created', 'messages'],
	['typing.user.start', 'messages'],
	['friend.request_sent', 'social'],
	['friend.request_accepted', 'social'],
	['group.member_added', 'social'],
	['agent.updated', 'settings'],
	['role.updated', 'settings'],
	['settings.updated', 'settings'],
	['user.preferences_updated', 'settings'],
	['user_client.preferences_updated', 'settings'],
]

const genericEventTypes = [
	'notification.custom',
	'access.updated',
	'citation.created',
	'memory.created',
	'run.started',
	'task.failed',
	'tool.called',
	'stream.chunk',
	'something.unknown',
]

describe('notificationAppId', () => {
	it('routes every known event type to the app that owns it', () => {
		for (const [eventType, appId] of appByEventType) {
			expect(notificationAppId(eventType)).toBe(appId)
		}
	})

	it('claims no app for generic, appless and unknown types', () => {
		for (const eventType of genericEventTypes) {
			expect(notificationAppId(eventType)).toBeNull()
		}
		expect(notificationAppId(null)).toBeNull()
		expect(notificationAppId(undefined)).toBeNull()
		expect(notificationAppId('')).toBeNull()
	})
})

describe('notificationIcon', () => {
	it('shows the app icon of the app the notification belongs to', () => {
		for (const [eventType, appId] of appByEventType) {
			expect(notificationIcon(eventType)).toBe(appIcon(appId))
		}
	})

	it('falls back to the generic notification icon instead of a wrong app icon', () => {
		for (const eventType of genericEventTypes) {
			expect(notificationIcon(eventType)).toBe(genericNotificationIcon)
		}
		expect(notificationIcon(null)).toBe(genericNotificationIcon)
	})

	it('keeps the generic icon out of the app icon set', () => {
		expect(appVisuals.some((app) => app.icon === genericNotificationIcon)).toBe(false)
	})
})

describe('notificationAccent', () => {
	it('draws the icon in the accent of the app that owns it', () => {
		for (const [eventType, appId] of appByEventType) {
			expect(notificationAccent(eventType)).toBe(appAccent(appId))
		}
	})

	it('falls back to the generic accent instead of some app colour', () => {
		for (const eventType of genericEventTypes) {
			expect(notificationAccent(eventType)).toBe(genericNotificationAccent)
		}
		expect(notificationAccent(null)).toBe(genericNotificationAccent)
		expect(notificationAccent(undefined)).toBe(genericNotificationAccent)
	})

	it('resolves to a real palette entry', () => {
		for (const [eventType] of [...appByEventType, ...genericEventTypes.map((t) => [t])]) {
			expect(accentColors[notificationAccent(eventType)]?.primary).toMatch(/^#/)
		}
	})
})
