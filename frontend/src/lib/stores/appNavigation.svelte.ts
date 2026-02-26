import { browser } from '$app/environment'

export type SettingsRouteId =
	| '/settings/appearance'
	| '/settings/notifications'
	| '/settings/privacy'
	| '/settings/accessibility'
	| '/settings/ai'
	| '/settings/security'
	| '/settings/advanced'
	| '/settings/about'
	| '/settings/debug'

export type NotesRouteId = '/notes' | `/notes/${string}`
export type RemindersRouteId = '/reminders' | `/reminders/lists/${string}`

export type SocialRouteId = '/social/friends' | '/social/groups'

export type AppId = 'settings' | 'notes' | 'reminders' | 'social'

export const DEFAULT_SETTINGS_ROUTE: SettingsRouteId = '/settings/appearance'
export const DEFAULT_NOTES_ROUTE: NotesRouteId = '/notes'
export const DEFAULT_REMINDERS_ROUTE: RemindersRouteId = '/reminders'
export const DEFAULT_SOCIAL_ROUTE: SocialRouteId = '/social/friends'

const STORAGE_PREFIX = 'last-visited-route:'

const SETTINGS_ROUTES: SettingsRouteId[] = [
	'/settings/appearance',
	'/settings/notifications',
	'/settings/privacy',
	'/settings/accessibility',
	'/settings/ai',
	'/settings/security',
	'/settings/advanced',
	'/settings/about',
	'/settings/debug',
]

function normalizePath(pathname: string): string {
	if (!pathname) return ''
	return pathname.endsWith('/') && pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
}

function isSettingsRoute(pathname: string): pathname is SettingsRouteId {
	return SETTINGS_ROUTES.some((route) => route === pathname)
}

function isNotesRoute(pathname: string): pathname is NotesRouteId {
	if (pathname === '/notes') return true
	return /^\/notes\/[^/]+$/.test(pathname)
}

function isRemindersRoute(pathname: string): pathname is RemindersRouteId {
	if (pathname === '/reminders') return true
	return /^\/reminders\/lists\/[^/]+$/.test(pathname)
}

function isSocialRoute(pathname: string): pathname is SocialRouteId {
	return pathname === '/social/friends' || pathname === '/social/groups'
}

function readStoredSettings(): SettingsRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}settings`) ?? ''
		const normalized = normalizePath(raw)
		return isSettingsRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredNotes(): NotesRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}notes`) ?? ''
		const normalized = normalizePath(raw)
		return isNotesRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredReminders(): RemindersRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}reminders`) ?? ''
		const normalized = normalizePath(raw)
		return isRemindersRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredSocial(): SocialRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}social`) ?? ''
		const normalized = normalizePath(raw)
		return isSocialRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

class AppNavigationStore {
	lastSettingsRoute = $state<SettingsRouteId | ''>(readStoredSettings())
	lastNotesRoute = $state<NotesRouteId | ''>(readStoredNotes())
	lastRemindersRoute = $state<RemindersRouteId | ''>(readStoredReminders())
	lastSocialRoute = $state<SocialRouteId | ''>(readStoredSocial())

	getEntryRoute(appId: 'settings'): SettingsRouteId
	getEntryRoute(appId: 'notes'): NotesRouteId
	getEntryRoute(appId: 'reminders'): RemindersRouteId
	getEntryRoute(appId: 'social'): SocialRouteId
	getEntryRoute(appId: AppId): SettingsRouteId | NotesRouteId | RemindersRouteId | SocialRouteId {
		switch (appId) {
			case 'settings':
				return this.lastSettingsRoute || DEFAULT_SETTINGS_ROUTE
			case 'notes':
				return this.lastNotesRoute || DEFAULT_NOTES_ROUTE
			case 'reminders':
				return this.lastRemindersRoute || DEFAULT_REMINDERS_ROUTE
			case 'social':
				return this.lastSocialRoute || DEFAULT_SOCIAL_ROUTE
		}
	}

	setLastVisited(appId: 'settings', pathname: string): void
	setLastVisited(appId: 'notes', pathname: string): void
	setLastVisited(appId: 'reminders', pathname: string): void
	setLastVisited(appId: 'social', pathname: string): void
	setLastVisited(appId: AppId, pathname: string): void {
		const normalized = normalizePath(pathname)

		switch (appId) {
			case 'settings': {
				if (!isSettingsRoute(normalized)) return
				this.lastSettingsRoute = normalized
				this.persist('settings', normalized)
				return
			}
			case 'notes': {
				if (!isNotesRoute(normalized)) return
				this.lastNotesRoute = normalized
				this.persist('notes', normalized)
				return
			}
			case 'reminders': {
				if (!isRemindersRoute(normalized)) return
				this.lastRemindersRoute = normalized
				this.persist('reminders', normalized)
				return
			}
			case 'social': {
				if (!isSocialRoute(normalized)) return
				this.lastSocialRoute = normalized
				this.persist('social', normalized)
				return
			}
		}
	}

	private persist(
		appId: AppId,
		pathname: SettingsRouteId | NotesRouteId | RemindersRouteId | SocialRouteId
	) {
		if (!browser) return
		try {
			window.localStorage.setItem(`${STORAGE_PREFIX}${appId}`, pathname)
		} catch {
			// ignore storage errors
		}
	}
}

export const appNavigation = new AppNavigationStore()
