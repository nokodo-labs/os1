import { browser } from '$app/environment'
import { device } from '$lib/stores/device.svelte'

export type SettingsSectionRouteId =
	| '/settings/appearance'
	| '/settings/notifications'
	| '/settings/privacy'
	| '/settings/accessibility'
	| '/settings/ai'
	| '/settings/security'
	| '/settings/advanced'
	| '/settings/about'
	| '/settings/debug'

export type SettingsRouteId = '/settings' | SettingsSectionRouteId

export type NotesRouteId = '/notes' | `/notes/${string}`
type ReminderListRouteId = `/reminders/lists/${string}`
export type RemindersRouteId = '/reminders' | '/reminders/lists' | ReminderListRouteId
export type CalendarRouteId = '/calendar'
export type MessagesRouteId = '/messages'
export type WebRouteId = '/web'
export type MediaRouteId = '/media/discover' | '/media/search' | '/media/movies' | '/media/shows'

export type SocialRouteId = '/social/friends' | '/social/groups'

export type ProjectsRouteId = '/projects' | `/projects/${string}`

export type AppId =
	| 'settings'
	| 'notes'
	| 'reminders'
	| 'calendar'
	| 'messages'
	| 'web'
	| 'media'
	| 'social'
	| 'projects'

/**
 * where inside an app the reader was standing.
 *
 * REGULAR (split view) keeps both panes on screen, so only the detail matters and the
 * level is ignored. COMPACT (one column) shows one of them at a time, so the master is
 * a destination of its own and has to be remembered as such - a pathname alone cannot
 * say "was at master" for apps whose master route is not a storable detail route.
 */
export type AppLevel = 'master' | 'detail'

export const DEFAULT_SETTINGS_ROUTE: SettingsRouteId = '/settings/appearance'
export const DEFAULT_NOTES_ROUTE: NotesRouteId = '/notes'
export const DEFAULT_REMINDERS_ROUTE: RemindersRouteId = '/reminders'
export const DEFAULT_CALENDAR_ROUTE: CalendarRouteId = '/calendar'
export const DEFAULT_MESSAGES_ROUTE: MessagesRouteId = '/messages'
export const DEFAULT_WEB_ROUTE: WebRouteId = '/web'
export const DEFAULT_MEDIA_ROUTE: MediaRouteId = '/media/discover'
export const DEFAULT_SOCIAL_ROUTE: SocialRouteId = '/social/friends'
export const DEFAULT_PROJECTS_ROUTE: ProjectsRouteId = '/projects'

// compact master routes: the standalone list view each app falls back to
export const MASTER_SETTINGS_ROUTE: SettingsRouteId = '/settings'
export const MASTER_NOTES_ROUTE: NotesRouteId = '/notes'
export const MASTER_REMINDERS_ROUTE: RemindersRouteId = '/reminders/lists'
export const MASTER_PROJECTS_ROUTE: ProjectsRouteId = '/projects'

const STORAGE_PREFIX = 'last-visited-route:'
const LEVEL_STORAGE_PREFIX = 'last-visited-level:'

// a record rather than a list, so a new AppId cannot be added without landing here
const KNOWN_APP_IDS: Record<AppId, true> = {
	settings: true,
	notes: true,
	reminders: true,
	calendar: true,
	messages: true,
	web: true,
	media: true,
	social: true,
	projects: true,
}

function isKnownAppId(value: string): boolean {
	return Object.hasOwn(KNOWN_APP_IDS, value)
}

/**
 * forget stored positions for apps that no longer exist - `research`, renamed to
 * `web`, still has keys in storage. nothing is migrated: the stored value is the
 * retired app's own pathname, which no surviving app would accept, so a migration
 * would write a value that every reader rejects (and could overwrite a real one).
 */
function pruneUnknownApps(): void {
	if (!browser) return
	try {
		const stale: string[] = []
		for (let index = 0; index < window.localStorage.length; index += 1) {
			const key = window.localStorage.key(index)
			if (key === null) continue
			let appId: string | null = null
			if (key.startsWith(STORAGE_PREFIX)) appId = key.slice(STORAGE_PREFIX.length)
			else if (key.startsWith(LEVEL_STORAGE_PREFIX))
				appId = key.slice(LEVEL_STORAGE_PREFIX.length)
			if (appId === null || isKnownAppId(appId)) continue
			stale.push(key)
		}
		for (const key of stale) window.localStorage.removeItem(key)
	} catch {
		// ignore storage errors
	}
}

const SETTINGS_SECTION_ROUTES: SettingsSectionRouteId[] = [
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

const MEDIA_ROUTES: MediaRouteId[] = [
	'/media/discover',
	'/media/search',
	'/media/movies',
	'/media/shows',
]

function normalizePath(pathname: string): string {
	if (!pathname) return ''
	return pathname.endsWith('/') && pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
}

function isSettingsSectionRoute(pathname: string): pathname is SettingsSectionRouteId {
	return SETTINGS_SECTION_ROUTES.some((route) => route === pathname)
}

function isNoteDetailRoute(pathname: string): boolean {
	return /^\/notes\/[^/]+$/.test(pathname)
}

function isNotesRoute(pathname: string): pathname is NotesRouteId {
	if (pathname === MASTER_NOTES_ROUTE) return true
	return isNoteDetailRoute(pathname)
}

function isReminderListRoute(pathname: string): pathname is ReminderListRouteId {
	return /^\/reminders\/lists\/[^/]+$/.test(pathname)
}

function isCalendarRoute(pathname: string): pathname is CalendarRouteId {
	return pathname === '/calendar'
}

function isMessagesRoute(pathname: string): pathname is MessagesRouteId {
	return pathname === '/messages'
}

function isWebRoute(pathname: string): pathname is WebRouteId {
	return pathname === '/web'
}

function isMediaRoute(pathname: string): pathname is MediaRouteId {
	return MEDIA_ROUTES.some((route) => route === pathname)
}

function isSocialRoute(pathname: string): pathname is SocialRouteId {
	return pathname === '/social/friends' || pathname === '/social/groups'
}

function isSocialDetailRoute(pathname: string): boolean {
	return /^\/social\/(groups|users)\/[^/]+$/.test(pathname)
}

function isProjectDetailRoute(pathname: string): boolean {
	return /^\/projects\/[^/]+$/.test(pathname)
}

function isProjectsRoute(pathname: string): pathname is ProjectsRouteId {
	if (pathname === MASTER_PROJECTS_ROUTE) return true
	return isProjectDetailRoute(pathname)
}

/**
 * classify a pathname as the app's master or one of its details.
 * returns null for paths the app does not own, and for transient redirect routes
 * (`/reminders`) that resolve to another level anyway.
 */
function resolveLevel(appId: AppId, pathname: string): AppLevel | null {
	switch (appId) {
		case 'settings':
			if (pathname === MASTER_SETTINGS_ROUTE) return 'master'
			return pathname.startsWith('/settings/') ? 'detail' : null
		case 'notes':
			if (pathname === MASTER_NOTES_ROUTE) return 'master'
			return isNoteDetailRoute(pathname) ? 'detail' : null
		case 'reminders':
			if (pathname === MASTER_REMINDERS_ROUTE) return 'master'
			return isReminderListRoute(pathname) ? 'detail' : null
		case 'projects':
			if (pathname === MASTER_PROJECTS_ROUTE) return 'master'
			return isProjectDetailRoute(pathname) ? 'detail' : null
		case 'social':
			if (isSocialRoute(pathname)) return 'master'
			return isSocialDetailRoute(pathname) ? 'detail' : null
		case 'calendar':
			return isCalendarRoute(pathname) ? 'master' : null
		case 'messages':
			return isMessagesRoute(pathname) ? 'master' : null
		case 'web':
			return isWebRoute(pathname) ? 'master' : null
		case 'media':
			return isMediaRoute(pathname) ? 'master' : null
	}
}

function readStoredSettings(): SettingsSectionRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}settings`) ?? ''
		const normalized = normalizePath(raw)
		return isSettingsSectionRoute(normalized) ? normalized : ''
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

function readStoredReminders(): ReminderListRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}reminders`) ?? ''
		const normalized = normalizePath(raw)
		return isReminderListRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredCalendar(): CalendarRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}calendar`) ?? ''
		const normalized = normalizePath(raw)
		return isCalendarRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredMessages(): MessagesRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}messages`) ?? ''
		const normalized = normalizePath(raw)
		return isMessagesRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredWeb(): WebRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}web`) ?? ''
		const normalized = normalizePath(raw)
		return isWebRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

function readStoredMedia(): MediaRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}media`) ?? ''
		const normalized = normalizePath(raw)
		return isMediaRoute(normalized) ? normalized : ''
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

function readStoredProjects(): ProjectsRouteId | '' {
	if (!browser) return ''
	try {
		const raw = window.localStorage.getItem(`${STORAGE_PREFIX}projects`) ?? ''
		const normalized = normalizePath(raw)
		return isProjectsRoute(normalized) ? normalized : ''
	} catch {
		return ''
	}
}

// an app nobody has opened yet starts at its master, the way a fresh app launch does
function readStoredLevel(appId: AppId): AppLevel {
	if (!browser) return 'master'
	try {
		const raw = window.localStorage.getItem(`${LEVEL_STORAGE_PREFIX}${appId}`)
		return raw === 'detail' ? 'detail' : 'master'
	} catch {
		return 'master'
	}
}

// runs before the store reads storage, so a retired app id never reaches a reader
pruneUnknownApps()

class AppNavigationStore {
	lastSettingsRoute = $state<SettingsSectionRouteId | ''>(readStoredSettings())
	lastNotesRoute = $state<NotesRouteId | ''>(readStoredNotes())
	lastRemindersRoute = $state<ReminderListRouteId | ''>(readStoredReminders())
	lastCalendarRoute = $state<CalendarRouteId | ''>(readStoredCalendar())
	lastMessagesRoute = $state<MessagesRouteId | ''>(readStoredMessages())
	lastWebRoute = $state<WebRouteId | ''>(readStoredWeb())
	lastMediaRoute = $state<MediaRouteId | ''>(readStoredMedia())
	lastSocialRoute = $state<SocialRouteId | ''>(readStoredSocial())
	lastProjectsRoute = $state<ProjectsRouteId | ''>(readStoredProjects())

	lastLevels = $state<Record<AppId, AppLevel>>({
		settings: readStoredLevel('settings'),
		notes: readStoredLevel('notes'),
		reminders: readStoredLevel('reminders'),
		calendar: readStoredLevel('calendar'),
		messages: readStoredLevel('messages'),
		web: readStoredLevel('web'),
		media: readStoredLevel('media'),
		social: readStoredLevel('social'),
		projects: readStoredLevel('projects'),
	})

	getEntryRoute(appId: 'settings'): SettingsRouteId
	getEntryRoute(appId: 'notes'): NotesRouteId
	getEntryRoute(appId: 'reminders'): RemindersRouteId
	getEntryRoute(appId: 'calendar'): CalendarRouteId
	getEntryRoute(appId: 'messages'): MessagesRouteId
	getEntryRoute(appId: 'web'): WebRouteId
	getEntryRoute(appId: 'media'): MediaRouteId
	getEntryRoute(appId: 'social'): SocialRouteId
	getEntryRoute(appId: 'projects'): ProjectsRouteId
	getEntryRoute(
		appId: AppId
	):
		| SettingsRouteId
		| NotesRouteId
		| RemindersRouteId
		| CalendarRouteId
		| MessagesRouteId
		| WebRouteId
		| MediaRouteId
		| SocialRouteId
		| ProjectsRouteId
	getEntryRoute(
		appId: AppId
	):
		| SettingsRouteId
		| NotesRouteId
		| RemindersRouteId
		| CalendarRouteId
		| MessagesRouteId
		| WebRouteId
		| MediaRouteId
		| SocialRouteId
		| ProjectsRouteId {
		switch (appId) {
			case 'settings':
				if (this.entersAtMaster('settings')) return MASTER_SETTINGS_ROUTE
				return this.lastSettingsRoute || DEFAULT_SETTINGS_ROUTE
			case 'notes':
				if (this.entersAtMaster('notes')) return MASTER_NOTES_ROUTE
				return this.lastNotesRoute || DEFAULT_NOTES_ROUTE
			case 'reminders':
				if (this.entersAtMaster('reminders')) return MASTER_REMINDERS_ROUTE
				return this.lastRemindersRoute || DEFAULT_REMINDERS_ROUTE
			case 'calendar':
				return this.lastCalendarRoute || DEFAULT_CALENDAR_ROUTE
			case 'messages':
				return this.lastMessagesRoute || DEFAULT_MESSAGES_ROUTE
			case 'web':
				return this.lastWebRoute || DEFAULT_WEB_ROUTE
			case 'media':
				return this.lastMediaRoute || DEFAULT_MEDIA_ROUTE
			case 'social':
				return this.lastSocialRoute || DEFAULT_SOCIAL_ROUTE
			case 'projects':
				if (this.entersAtMaster('projects')) return MASTER_PROJECTS_ROUTE
				return this.lastProjectsRoute || DEFAULT_PROJECTS_ROUTE
		}
	}

	getLastLevel(appId: AppId): AppLevel {
		return this.lastLevels[appId]
	}

	setLastVisited(appId: 'settings', pathname: string): void
	setLastVisited(appId: 'notes', pathname: string): void
	setLastVisited(appId: 'reminders', pathname: string): void
	setLastVisited(appId: 'calendar', pathname: string): void
	setLastVisited(appId: 'messages', pathname: string): void
	setLastVisited(appId: 'web', pathname: string): void
	setLastVisited(appId: 'media', pathname: string): void
	setLastVisited(appId: 'social', pathname: string): void
	setLastVisited(appId: 'projects', pathname: string): void
	setLastVisited(appId: AppId, pathname: string): void
	setLastVisited(appId: AppId, pathname: string): void {
		const normalized = normalizePath(pathname)

		this.setLevel(appId, resolveLevel(appId, normalized))

		switch (appId) {
			case 'settings': {
				if (!isSettingsSectionRoute(normalized)) return
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
				if (!isReminderListRoute(normalized)) return
				this.lastRemindersRoute = normalized
				this.persist('reminders', normalized)
				return
			}
			case 'calendar': {
				if (!isCalendarRoute(normalized)) return
				this.lastCalendarRoute = normalized
				this.persist('calendar', normalized)
				return
			}
			case 'messages': {
				if (!isMessagesRoute(normalized)) return
				this.lastMessagesRoute = normalized
				this.persist('messages', normalized)
				return
			}
			case 'web': {
				if (!isWebRoute(normalized)) return
				this.lastWebRoute = normalized
				this.persist('web', normalized)
				return
			}
			case 'media': {
				if (!isMediaRoute(normalized)) return
				this.lastMediaRoute = normalized
				this.persist('media', normalized)
				return
			}
			case 'social': {
				if (!isSocialRoute(normalized)) return
				this.lastSocialRoute = normalized
				this.persist('social', normalized)
				return
			}
			case 'projects': {
				if (!isProjectsRoute(normalized)) return
				this.lastProjectsRoute = normalized
				this.persist('projects', normalized)
				return
			}
		}
	}

	// only compact re-enters at the master; regular keeps both panes visible
	private entersAtMaster(appId: AppId): boolean {
		return device.isMobile && this.lastLevels[appId] === 'master'
	}

	private setLevel(appId: AppId, level: AppLevel | null) {
		if (!level) return
		if (this.lastLevels[appId] === level) return
		this.lastLevels[appId] = level
		if (!browser) return
		try {
			window.localStorage.setItem(`${LEVEL_STORAGE_PREFIX}${appId}`, level)
		} catch {
			// ignore storage errors
		}
	}

	private persist(
		appId: AppId,
		pathname:
			| SettingsRouteId
			| NotesRouteId
			| RemindersRouteId
			| CalendarRouteId
			| MessagesRouteId
			| WebRouteId
			| MediaRouteId
			| SocialRouteId
			| ProjectsRouteId
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
