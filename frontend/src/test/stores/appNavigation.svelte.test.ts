/**
 * app entry restore: COMPACT remembers whether the reader left at the master or
 * inside a detail, REGULAR keeps restoring the detail, and explicit destinations
 * always beat the remembered position.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: true }))

type AppNavigationModule = typeof import('$lib/stores/appNavigation.svelte')
type DeviceState = (typeof import('$lib/stores/device.svelte'))['device']

/** fresh store + device pair, rehydrated from whatever localStorage holds. */
async function loadStores(compact: boolean): Promise<{
	appNavigation: AppNavigationModule['appNavigation']
	device: DeviceState
}> {
	vi.resetModules()
	const { device } = await import('$lib/stores/device.svelte')
	const { appNavigation } = await import('$lib/stores/appNavigation.svelte')
	device.isMobile = compact
	return { appNavigation, device }
}

beforeEach(() => {
	window.localStorage.clear()
})

describe('compact restore', () => {
	it('reopens at the master when the reader left at the master', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('settings', '/settings/ai')
		appNavigation.setLastVisited('settings', '/settings')
		expect(appNavigation.getEntryRoute('settings')).toBe('/settings')

		appNavigation.setLastVisited('notes', '/notes/note_1')
		appNavigation.setLastVisited('notes', '/notes')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes')

		appNavigation.setLastVisited('reminders', '/reminders/lists/list_1')
		appNavigation.setLastVisited('reminders', '/reminders/lists')
		expect(appNavigation.getEntryRoute('reminders')).toBe('/reminders/lists')

		appNavigation.setLastVisited('projects', '/projects/project_1')
		appNavigation.setLastVisited('projects', '/projects')
		expect(appNavigation.getEntryRoute('projects')).toBe('/projects')
	})

	it('reopens at the detail when the reader left inside one', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('settings', '/settings')
		appNavigation.setLastVisited('settings', '/settings/ai')
		expect(appNavigation.getEntryRoute('settings')).toBe('/settings/ai')

		appNavigation.setLastVisited('notes', '/notes')
		appNavigation.setLastVisited('notes', '/notes/note_1')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes/note_1')

		appNavigation.setLastVisited('reminders', '/reminders/lists')
		appNavigation.setLastVisited('reminders', '/reminders/lists/list_1')
		expect(appNavigation.getEntryRoute('reminders')).toBe('/reminders/lists/list_1')

		appNavigation.setLastVisited('projects', '/projects')
		appNavigation.setLastVisited('projects', '/projects/project_1')
		expect(appNavigation.getEntryRoute('projects')).toBe('/projects/project_1')
	})

	it('opens flat and tabbed apps at their own route', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('messages', '/messages')
		appNavigation.setLastVisited('calendar', '/calendar')
		appNavigation.setLastVisited('social', '/social/groups')
		appNavigation.setLastVisited('media', '/media/shows')

		expect(appNavigation.getEntryRoute('messages')).toBe('/messages')
		expect(appNavigation.getEntryRoute('calendar')).toBe('/calendar')
		expect(appNavigation.getEntryRoute('social')).toBe('/social/groups')
		expect(appNavigation.getEntryRoute('media')).toBe('/media/shows')
	})

	it('sends a tabbed app to its default tab when nothing is remembered', async () => {
		const { appNavigation } = await loadStores(true)

		// the group root is a redirect, never a destination worth remembering
		appNavigation.setLastVisited('media', '/media')

		expect(appNavigation.getEntryRoute('media')).toBe('/media/discover')
	})
})

describe('regular restore', () => {
	it('is unchanged by the remembered level', async () => {
		const { appNavigation } = await loadStores(false)

		// the master is a permanently visible pane, so the detail is what gets restored
		appNavigation.setLastVisited('settings', '/settings/ai')
		appNavigation.setLastVisited('settings', '/settings')
		expect(appNavigation.getEntryRoute('settings')).toBe('/settings/ai')

		appNavigation.setLastVisited('reminders', '/reminders/lists/list_1')
		appNavigation.setLastVisited('reminders', '/reminders/lists')
		expect(appNavigation.getEntryRoute('reminders')).toBe('/reminders/lists/list_1')

		// apps whose master route is itself storable keep returning that stored path
		appNavigation.setLastVisited('notes', '/notes/note_1')
		appNavigation.setLastVisited('notes', '/notes')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes')
	})

	it('falls back to the app default with no memory', async () => {
		const { appNavigation } = await loadStores(false)

		expect(appNavigation.getEntryRoute('settings')).toBe('/settings/appearance')
		expect(appNavigation.getEntryRoute('reminders')).toBe('/reminders')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes')
	})
})

describe('level tracking', () => {
	it('going back from a detail to the master updates the level', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('notes', '/notes/note_1')
		expect(appNavigation.getLastLevel('notes')).toBe('detail')

		appNavigation.setLastVisited('notes', '/notes')
		expect(appNavigation.getLastLevel('notes')).toBe('master')
	})

	it('survives a reload', async () => {
		const first = await loadStores(true)
		first.appNavigation.setLastVisited('settings', '/settings/ai')
		first.appNavigation.setLastVisited('settings', '/settings')

		const reloaded = await loadStores(true)
		expect(reloaded.appNavigation.getLastLevel('settings')).toBe('master')
		expect(reloaded.appNavigation.getEntryRoute('settings')).toBe('/settings')

		reloaded.appNavigation.setLastVisited('settings', '/settings/privacy')

		const again = await loadStores(true)
		expect(again.appNavigation.getLastLevel('settings')).toBe('detail')
		expect(again.appNavigation.getEntryRoute('settings')).toBe('/settings/privacy')
	})

	it('ignores the transient /reminders redirect route', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('reminders', '/reminders/lists/list_1')
		appNavigation.setLastVisited('reminders', '/reminders')

		expect(appNavigation.getLastLevel('reminders')).toBe('detail')
		expect(appNavigation.getEntryRoute('reminders')).toBe('/reminders/lists/list_1')
	})
})

describe('retired app ids', () => {
	it('drops stored entries for apps that no longer exist', async () => {
		window.localStorage.setItem('last-visited-route:research', '/research')
		window.localStorage.setItem('last-visited-level:research', 'detail')

		await loadStores(true)

		expect(window.localStorage.getItem('last-visited-route:research')).toBe(null)
		expect(window.localStorage.getItem('last-visited-level:research')).toBe(null)
	})

	it('leaves surviving apps and unrelated keys alone', async () => {
		window.localStorage.setItem('last-visited-route:research', '/research')
		window.localStorage.setItem('last-visited-route:web', '/web')
		window.localStorage.setItem('last-visited-level:notes', 'detail')
		window.localStorage.setItem('theme', 'dark')

		const { appNavigation } = await loadStores(true)

		expect(window.localStorage.getItem('last-visited-route:web')).toBe('/web')
		expect(window.localStorage.getItem('last-visited-level:notes')).toBe('detail')
		expect(window.localStorage.getItem('theme')).toBe('dark')
		expect(appNavigation.getEntryRoute('web')).toBe('/web')
		expect(appNavigation.getLastLevel('notes')).toBe('detail')
	})

	it('does not adopt a retired app path as the renamed app position', async () => {
		window.localStorage.setItem('last-visited-route:research', '/research/deep')

		const { appNavigation } = await loadStores(true)

		expect(appNavigation.getEntryRoute('web')).toBe('/web')
	})
})

describe('explicit destinations', () => {
	it('a deep link into a detail beats a remembered master', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('notes', '/notes')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes')

		// arriving straight at a note (notification tap, search hit, "chat about this")
		appNavigation.setLastVisited('notes', '/notes/note_9')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes/note_9')
	})

	it('a deep link into the master beats a remembered detail', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('projects', '/projects/project_1')
		expect(appNavigation.getEntryRoute('projects')).toBe('/projects/project_1')

		appNavigation.setLastVisited('projects', '/projects')
		expect(appNavigation.getEntryRoute('projects')).toBe('/projects')
	})

	it('reading the entry route never moves the remembered position', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('notes', '/notes/note_1')
		appNavigation.getEntryRoute('notes')
		appNavigation.getEntryRoute('notes')

		expect(appNavigation.getLastLevel('notes')).toBe('detail')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes/note_1')
	})

	it('leaves an app untouched when the destination belongs elsewhere', async () => {
		const { appNavigation } = await loadStores(true)

		appNavigation.setLastVisited('notes', '/notes/note_1')
		appNavigation.setLastVisited('notes', '/c/thread_1')

		expect(appNavigation.getLastLevel('notes')).toBe('detail')
		expect(appNavigation.getEntryRoute('notes')).toBe('/notes/note_1')
	})
})
