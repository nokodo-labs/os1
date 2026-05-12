import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { agents } from '$lib/stores/agents.svelte'
import type { ApiCacheStore, RefreshableStore } from '$lib/stores/cacheLifecycle'
import { calendarEvents, calendars, scheduledItems } from '$lib/stores/calendars.svelte'
import { chat } from '$lib/stores/chat.svelte'
import { files } from '$lib/stores/files.svelte'
import { friends } from '$lib/stores/friends.svelte'
import { groups } from '$lib/stores/groups.svelte'
import { notes } from '$lib/stores/notes.svelte'
import { notifications } from '$lib/stores/notifications.svelte'
import { permissions } from '$lib/stores/permissions.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { projects } from '$lib/stores/projects.svelte'
import { reminders } from '$lib/stores/reminders.svelte'
import { resourceAccess } from '$lib/stores/resourceAccess.svelte'
import { session } from '$lib/stores/session.svelte'
import { settingsCache } from '$lib/stores/settings.svelte'

export const apiCacheStores = [
	{
		id: 'agents',
		invalidate: () => agents.invalidate(),
		shouldRefresh: () => agents.hasLoaded,
		refresh: () => agents.refresh(),
		clear: () => agents.clear(),
	},
	{
		id: 'notifications',
		invalidate: () => notifications.invalidate(),
		shouldRefresh: () => notifications.initialized,
		refresh: () => notifications.refresh(),
		clear: () => notifications.clear(),
	},
	{
		id: 'chat',
		invalidate: () => chat.invalidate(),
		refresh: () => chat.refresh(),
		clear: () => chat.clear(),
	},
	{
		id: 'activeRuns',
		invalidate: () => activeRunsStore.invalidate(),
		refresh: () => activeRunsStore.refresh(),
		clear: () => activeRunsStore.clear(),
	},
	{
		id: 'notes',
		invalidate: () => notes.invalidate(),
		shouldRefresh: () => notes.hasLoaded,
		refresh: () => notes.refresh(),
		clear: () => notes.clear(),
	},
	{
		id: 'projects',
		invalidate: () => projects.invalidate(),
		shouldRefresh: () => projects.hasLoaded,
		refresh: () => projects.refresh(),
		clear: () => projects.clear(),
	},
	{
		id: 'calendars',
		invalidate: () => calendars.invalidate(),
		shouldRefresh: () => calendars.hasLoaded,
		refresh: () => calendars.refresh(),
		clear: () => calendars.clear(),
	},
	{
		id: 'calendarEvents',
		invalidate: () => calendarEvents.invalidate(),
		shouldRefresh: () => calendarEvents.hasLoaded,
		refresh: () => calendarEvents.refresh(),
		clear: () => calendarEvents.clear(),
	},
	{
		id: 'scheduledItems',
		invalidate: () => scheduledItems.invalidate(),
		shouldRefresh: () => scheduledItems.hasLoaded,
		refresh: () => scheduledItems.refresh(),
		clear: () => scheduledItems.clear(),
	},
	{
		id: 'reminders',
		invalidate: () => reminders.invalidate(),
		shouldRefresh: () => reminders.hasLoaded,
		refresh: () => reminders.refresh(),
		clear: () => reminders.clear(),
	},
	{
		id: 'settings',
		invalidate: () => settingsCache.invalidate(),
		refresh: () => settingsCache.refresh(),
		clear: () => settingsCache.clear(),
	},
	{
		id: 'files',
		invalidate: () => files.invalidate(),
		shouldRefresh: () => files.hasLoaded,
		refresh: () => files.refresh(),
		clear: () => files.clear(),
	},
	{
		id: 'friends',
		invalidate: () => friends.invalidate(),
		shouldRefresh: () => friends.isReady,
		refresh: () => friends.refresh(),
		clear: () => friends.clear(),
	},
	{
		id: 'groups',
		invalidate: () => groups.invalidate(),
		shouldRefresh: () => groups.hasLoaded,
		refresh: () => groups.refresh(),
		clear: () => groups.clear(),
	},
	{
		id: 'permissions',
		invalidate: () => permissions.invalidate(),
		shouldRefresh: () => permissions.list !== null,
		refresh: () => permissions.refresh(),
		clear: () => permissions.clear(),
	},
	{
		id: 'resourceAccess',
		invalidate: () => resourceAccess.invalidate(),
		refresh: () => resourceAccess.refresh(),
		clear: () => resourceAccess.clear(),
	},
] satisfies readonly ApiCacheStore[]

export const resumeRefreshStores = [
	{ id: 'session', refresh: () => session.refresh() },
	{ id: 'preferences', refresh: () => preferences.refresh() },
] satisfies readonly RefreshableStore[]
