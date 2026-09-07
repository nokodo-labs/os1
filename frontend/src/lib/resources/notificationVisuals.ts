import AppNotification from '$lib/components/icons/AppNotification.svelte'
import type { AccentColorKey } from '$lib/contexts/themeContext.svelte'
import { appVisuals, type AppVisualId, type ResourceIconComponent } from './resourceVisuals'

/** shown when a notification belongs to no app (custom and system notifications). */
export const genericNotificationIcon: ResourceIconComponent = AppNotification

/**
 * the accent an appless notification borrows: the same blue the dock itself
 * carries in the homepage suggestions, so the generic bell never reads as
 * some app's colour.
 */
export const genericNotificationAccent: AccentColorKey = 'blue'

/**
 * the app a notification belongs to, taken from the event type backing it.
 * `notification.*` types name their own source, every other type is `<domain>.<action>`.
 */
export function notificationAppId(eventType: string | null | undefined): AppVisualId | null {
	if (!eventType) return null

	if (eventType.startsWith('notification.')) {
		switch (eventType) {
			case 'notification.reminder_alert':
				return 'reminders'
			case 'notification.calendar_event_alert':
				return 'calendar'
			case 'notification.agent':
				return 'messages'
			default:
				return null
		}
	}

	switch (eventType.split('.')[0]) {
		case 'reminder':
		case 'reminder_list':
			return 'reminders'
		case 'calendar':
			return 'calendar'
		case 'note':
			return 'notes'
		case 'file':
			return 'library'
		case 'project':
			return 'projects'
		case 'thread':
		case 'message':
		case 'typing':
			return 'messages'
		case 'friend':
		case 'group':
			return 'social'
		case 'agent':
		case 'role':
		case 'settings':
		case 'user':
		case 'user_client':
			return 'settings'
		default:
			return null
	}
}

/** the app icon a notification row or toast shows for its type. */
export function notificationIcon(eventType: string | null | undefined): ResourceIconComponent {
	const appId = notificationAppId(eventType)
	if (!appId) return genericNotificationIcon
	return appVisuals.find((app) => app.id === appId)?.icon ?? genericNotificationIcon
}

/**
 * the accent colour that icon is drawn in - the owning app's own accent, off
 * the same `appVisuals` entries the apps grid tints its tiles with, so a
 * notification is placeable by colour before its text is read.
 */
export function notificationAccent(eventType: string | null | undefined): AccentColorKey {
	const appId = notificationAppId(eventType)
	if (!appId) return genericNotificationAccent
	return appVisuals.find((app) => app.id === appId)?.accent ?? genericNotificationAccent
}
