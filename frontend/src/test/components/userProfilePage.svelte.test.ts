/**
 * the user profile page: an instagram-scale identity header, a row of action
 * tiles gated on the relationship, ios-contacts style grouped sections, and the
 * destructive actions kept last.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

interface Row {
	id: string
	[key: string]: unknown
}

const state = vi.hoisted(() => ({
	pageUserId: 'user_alice',
	currentUserId: 'user_me' as string | null,
	token: 'header.token.signature' as string | null,
	friends: [] as Row[],
	incoming: [] as Row[],
	outgoing: [] as Row[],
	groups: [] as Row[],
	blocks: [] as Row[],
	conversations: [] as Row[],
	summaries: new Map<string, Row | null>(),
	currentUser: null as Row | null,
	account: {
		bio: null as string | null,
		birthDate: null as string | null,
		gender: null as string | null,
	},
	fullUserAllowed: false,
}))

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

vi.mock('$app/state', () => ({
	page: {
		get params() {
			return { id: state.pageUserId }
		},
		url: new URL('https://nokodo.test/social/users/user_alice'),
	},
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn(async (path: string) => {
			if (path === '/v1/users/{user_id}/friends') return { data: state.friends, error: null }
			if (path === '/v1/users/{user_id}/friends/requests/incoming')
				return { data: state.incoming, error: null }
			if (path === '/v1/users/{user_id}/friends/requests/outgoing')
				return { data: state.outgoing, error: null }
			if (path === '/v1/users/{user_id}/blocks') return { data: state.blocks, error: null }
			if (path === '/v1/groups') return { data: state.groups, error: null }
			if (path === '/v1/users/{user_id}')
				return state.fullUserAllowed
					? { data: state.currentUser, error: null }
					: { data: null, error: { detail: 'forbidden' } }
			return { data: [], error: null }
		}),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => state.token),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/contexts/systemChromeContext.svelte', () => ({
	useSystemChrome: () => ({ setContextActions: () => {} }),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		get currentUser() {
			return state.currentUser
		},
		get currentUserId() {
			return state.currentUserId
		},
		get userDisplay() {
			return { name: 'me', email: 'me@nokodo.net', avatar: null }
		},
		getUserSummary: (userId: string) => state.summaries.get(userId) ?? null,
		ensureUsers: vi.fn().mockResolvedValue(undefined),
	},
}))

vi.mock('$lib/stores/messages.svelte', () => ({
	messages: {
		get conversations() {
			return state.conversations
		},
		load: vi.fn().mockResolvedValue(undefined),
		createThread: vi.fn().mockResolvedValue(null),
	},
}))

vi.mock('$lib/stores/notifications.svelte', () => ({
	notifications: { pushEphemeralToast: vi.fn() },
	showError: vi.fn(),
}))

vi.mock('$lib/stores/preferences.svelte', () => ({
	preferences: {
		get data() {
			return { account: state.account }
		},
		update: vi.fn().mockResolvedValue(undefined),
	},
}))

const { friends } = await import('$lib/stores/friends.svelte')
const { groups } = await import('$lib/stores/groups.svelte')
const { modals } = await import('$lib/stores/modals.svelte')
const { api } = await import('$lib/api/client')
const ProfilePage = (await import('../../routes/social/users/[id]/+page.svelte')).default

function friendRow(id: string, name: string): Row {
	return { id, friendship_id: `fr_${id}`, username: name, display_name: name, avatar_url: null }
}

function groupRow(id: string, name: string, members: number): Row {
	return {
		id,
		name,
		owner_id: 'user_me',
		memberships: Array.from({ length: members }, (_, index) => ({ id: `m_${index}` })),
	}
}

function summary(id: string, name: string): Row {
	return { id, username: name, display_name: name, avatar_url: null }
}

function sectionOrder(): string[] {
	return [...document.body.querySelectorAll('section[data-section]')].map(
		(section) => section.getAttribute('data-section') ?? ''
	)
}

function tile(name: string): HTMLButtonElement | null {
	const buttons = [...document.body.querySelectorAll('button')]
	return buttons.find((button) => button.textContent?.trim() === name) ?? null
}

function statValue(label: string): string | null {
	const node = document.body.querySelector(`[data-stat="${label}"]`)
	return node?.querySelector('span')?.textContent?.trim() ?? null
}

async function renderPage(): Promise<void> {
	render(ProfilePage)
	await vi.waitFor(() => expect(document.body.querySelector('[data-identity]')).not.toBeNull())
}

describe('user profile page', () => {
	beforeEach(() => {
		cleanup()
		modals.close()
		friends.clear()
		groups.clear()
		state.pageUserId = 'user_alice'
		state.currentUserId = 'user_me'
		state.token = `header.${btoa(JSON.stringify({ sub: 'user_me' }))}.signature`
		state.friends = []
		state.incoming = []
		state.outgoing = []
		state.groups = []
		state.blocks = []
		state.conversations = []
		state.summaries = new Map([['user_alice', summary('user_alice', 'alice')]])
		state.currentUser = {
			id: 'user_me',
			username: 'me',
			display_name: 'me',
			avatar_url: null,
			bio: null,
		}
		state.account = { bio: null, birthDate: null, gender: null }
		state.fullUserAllowed = false
	})

	it('leads with the identity header: big avatar, name, handle', async () => {
		await renderPage()
		const header = document.body.querySelector('[data-identity]')
		expect(header?.querySelector('h1')?.textContent?.trim()).toBe('alice')
		expect(header?.textContent).toContain('@alice')
		// instagram-scale: the header avatar is the size-32 circle
		expect(header?.querySelector('.size-32')).not.toBeNull()
	})

	it('falls back to the bulk lookup when the full user record is forbidden', async () => {
		await renderPage()
		expect(api.GET).toHaveBeenCalledWith('/v1/users/{user_id}', expect.anything())
		expect(document.body.querySelector('[data-identity] h1')?.textContent?.trim()).toBe('alice')
	})

	it('shows the not-found state when the person cannot be read at all', async () => {
		state.summaries = new Map()
		render(ProfilePage)
		await vi.waitFor(() =>
			expect(document.body.querySelector('[data-empty-state]')).not.toBeNull()
		)
		expect(screen.getByText('profile not found')).toBeTruthy()
		expect(sectionOrder()).toEqual([])
	})

	it('summarises another person with mutual groups and shared chats only', async () => {
		state.groups = [groupRow('grp_1', 'weekend crew', 3)]
		state.conversations = [
			{ id: 't1', participants: [{ kind: 'user', user: { id: 'user_alice' } }] },
			{ id: 't2', participants: [{ kind: 'user', user: { id: 'user_bob' } }] },
		]
		await renderPage()
		expect(statValue('mutual groups')).toBe('1')
		expect(statValue('chats')).toBe('1')
		expect(document.body.querySelector('[data-stat="friends"]')).toBeNull()
	})

	it('summarises your own profile with friends and groups', async () => {
		state.pageUserId = 'user_me'
		state.friends = [friendRow('user_alice', 'alice'), friendRow('user_bob', 'bob')]
		state.groups = [groupRow('grp_1', 'weekend crew', 3)]
		await renderPage()
		expect(statValue('friends')).toBe('2')
		expect(statValue('groups')).toBe('1')
	})

	it('offers message, add friend and share to a stranger', async () => {
		await renderPage()
		expect(tile('message')).not.toBeNull()
		expect(tile('add friend')).not.toBeNull()
		expect(tile('share')).not.toBeNull()
	})

	it('swaps add friend for accept and decline on an incoming request', async () => {
		state.incoming = [{ id: 'fr_in', requester_id: 'user_alice', addressee_id: 'user_me' }]
		await renderPage()
		expect(tile('add friend')).toBeNull()
		expect(tile('accept')).not.toBeNull()
		expect(tile('decline')).not.toBeNull()
	})

	it('swaps add friend for cancel request on an outgoing request', async () => {
		state.outgoing = [{ id: 'fr_out', requester_id: 'user_me', addressee_id: 'user_alice' }]
		await renderPage()
		expect(tile('add friend')).toBeNull()
		expect(tile('cancel request')).not.toBeNull()
	})

	it('drops add friend once you are already friends', async () => {
		state.friends = [friendRow('user_alice', 'alice')]
		await renderPage()
		expect(tile('add friend')).toBeNull()
		expect(tile('message')).not.toBeNull()
	})

	it('runs the sections about, groups, then destructive last', async () => {
		await renderPage()
		expect(sectionOrder()).toEqual(['about', 'groups', 'destructive'])
	})

	it('keeps the destructive section off your own profile', async () => {
		state.pageUserId = 'user_me'
		await renderPage()
		expect(sectionOrder()).toEqual(['about', 'groups'])
	})

	it('does not pretend to have a shared resources section', async () => {
		await renderPage()
		expect(sectionOrder()).not.toContain('shared-resources')
		expect(document.body.textContent).not.toContain('shared resources')
	})

	it('lists mutual groups from the member-filtered group query', async () => {
		state.groups = [groupRow('grp_1', 'weekend crew', 3)]
		await renderPage()
		expect(api.GET).toHaveBeenCalledWith('/v1/groups', {
			params: { query: { member_user_id: 'user_alice' } },
		})
		const section = document.body.querySelector('section[data-section="groups"]')
		expect(section?.textContent).toContain('mutual groups')
		expect(section?.textContent).toContain('weekend crew')
		expect(section?.textContent).toContain('3 members')
	})

	it('offers unfriend only to friends, and only through the confirm dialog', async () => {
		await renderPage()
		expect(tile('unfriend')).toBeNull()
		cleanup()

		state.friends = [friendRow('user_alice', 'alice')]
		friends.clear()
		await renderPage()
		const unfriend = tile('unfriend')
		expect(unfriend).not.toBeNull()
		if (!unfriend) return
		await fireEvent.click(unfriend)
		expect(modals.active).toBe('confirm-delete')
		expect(modals.confirmDeletePayload?.confirmLabel).toBe('unfriend')
	})

	it('sends block through the confirm dialog', async () => {
		await renderPage()
		const block = tile('block')
		expect(block).not.toBeNull()
		if (!block) return
		await fireEvent.click(block)
		expect(modals.active).toBe('confirm-delete')
		expect(modals.confirmDeletePayload?.confirmLabel).toBe('block')
	})

	it('replaces block with unblock when the person is already blocked', async () => {
		state.blocks = [{ id: 'blk_1', blocker_id: 'user_me', blocked_id: 'user_alice' }]
		await renderPage()
		expect(tile('block')).toBeNull()
		expect(tile('unblock')).not.toBeNull()
		expect(document.body.querySelector('[data-identity]')?.textContent).toContain('blocked')
	})

	it('reveals the profile and about fields behind the edit tile', async () => {
		state.pageUserId = 'user_me'
		await renderPage()
		const edit = tile('edit profile')
		expect(edit).not.toBeNull()
		if (!edit) return
		await fireEvent.click(edit)
		expect(sectionOrder()).toEqual(['profile', 'about', 'groups'])
		expect(document.body.querySelector('#edit-name')).not.toBeNull()
		expect(document.body.querySelector('#edit-username')).not.toBeNull()
		expect(document.body.querySelector('#edit-bio')).not.toBeNull()
		expect(document.body.querySelector('#edit-birthdate')).not.toBeNull()
		expect(tile('done')).not.toBeNull()
	})

	it('shows your own gender and age in the about section', async () => {
		state.pageUserId = 'user_me'
		state.account = { bio: null, birthDate: '1996-01-01', gender: 'non-binary' }
		state.currentUser = {
			id: 'user_me',
			username: 'me',
			display_name: 'me',
			avatar_url: null,
			bio: 'builds things',
		}
		await renderPage()
		const about = document.body.querySelector('section[data-section="about"]')
		expect(about?.textContent).toContain('builds things')
		expect(about?.textContent).toContain('non-binary')
		expect(about?.textContent).toContain('years old')
	})
})
