import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { agents } from '$lib/stores/agents.svelte'
import type { ApiCacheStore, RefreshableStore } from '$lib/stores/cacheLifecycle'
import { calendarEvents, calendars, scheduledItems } from '$lib/stores/calendars.svelte'
import { chat } from '$lib/stores/chat.svelte'
import { files } from '$lib/stores/files.svelte'
import { friends } from '$lib/stores/friends.svelte'
import { groups } from '$lib/stores/groups.svelte'
import { mcpServers } from '$lib/stores/mcpServers.svelte'
import { messages } from '$lib/stores/messages.svelte'
import { notes } from '$lib/stores/notes.svelte'
import { notifications } from '$lib/stores/notifications.svelte'
import { permissions } from '$lib/stores/permissions.svelte'
import { preferences } from '$lib/stores/preferences.svelte'
import { projects } from '$lib/stores/projects.svelte'
import { reminders } from '$lib/stores/reminders.svelte'
import { resourceAccess } from '$lib/stores/resourceAccess.svelte'
import { settingsCache, settingsState } from '$lib/stores/settings.svelte'

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
		shouldRefresh: () => notifications.hasLoaded,
		refresh: () => notifications.refresh(),
		clear: () => notifications.clear(),
	},
	{
		id: 'chat',
		invalidate: () => chat.invalidate(),
		shouldRefresh: () => chat.hasLoaded,
		refresh: () => chat.refresh(),
		clear: () => chat.clear(),
	},
	{
		id: 'messages',
		invalidate: () => messages.invalidate(),
		shouldRefresh: () => messages.hasLoaded,
		refresh: () => messages.refresh(),
		clear: () => messages.clear(),
	},
	{
		id: 'activeRuns',
		invalidate: () => activeRunsStore.invalidate(),
		// live run map, no loaded-once collection: always safe to refetch.
		shouldRefresh: () => true,
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
		shouldRefresh: () => settingsState.hasLoaded,
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
		shouldRefresh: () => friends.hasLoaded,
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
		id: 'mcpServers',
		invalidate: () => mcpServers.invalidate(),
		shouldRefresh: () => mcpServers.hasLoaded,
		refresh: () => mcpServers.refresh(),
		clear: () => mcpServers.clear(),
	},
	{
		id: 'permissions',
		invalidate: () => permissions.invalidate(),
		shouldRefresh: () => permissions.hasLoaded,
		refresh: () => permissions.refresh(),
		clear: () => permissions.clear(),
	},
	{
		id: 'resourceAccess',
		invalidate: () => resourceAccess.invalidate(),
		// per-resource on-demand cache, no loaded-once collection: refetch reloads
		// whatever scopes are currently held.
		shouldRefresh: () => true,
		refresh: () => resourceAccess.refresh(),
		clear: () => resourceAccess.clear(),
	},
] satisfies readonly ApiCacheStore[]

/**
 * stores the resume path re-reads after a gap where live events were missed.
 * these are not `apiCacheStores`: nothing marks them stale, so they are refetched
 * directly. preferences is the only one that needs it - its cross-session updates
 * arrive as `user.preferences_updated` on the stream, which is exactly what a gap
 * drops. `preferences.refresh()` re-reads `GET /v1/users/{id}` and writes the
 * fresh user back onto the session, so adding `session.refresh()` here would only
 * repeat that same request.
 */
export const resumeRefreshStores = [
	{ id: 'preferences', refresh: () => preferences.refresh() },
] satisfies readonly RefreshableStore[]
