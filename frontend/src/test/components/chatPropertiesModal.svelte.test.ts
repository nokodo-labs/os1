/**
 * the chat info modal: an identity header, action tiles, grouped sections, and
 * the destructive actions kept last.
 */

import type { components } from '$lib/api/types'
import { fireEvent, render, screen, within } from '@testing-library/svelte'
import { afterEach, describe, expect, it, vi } from 'vitest'

type Thread = components['schemas']['Thread']
type Participant = NonNullable<Thread['participants']>[number]

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }))

vi.mock('$app/paths', () => ({ resolve: (path: string) => path }))

vi.mock('$app/state', () => ({ page: { url: new URL('https://nokodo.test/messages') } }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: [], error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

// the per-user writes (mute, mark read) read the signed-in id off the token.
const auth = vi.hoisted(() => ({ token: null as string | null }))
const userToken = `header.${btoa(JSON.stringify({ sub: 'user_me' }))}.signature`

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => auth.token),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		currentUserId: 'user_me',
		authorLabel: () => 'me',
		ensureUsers: vi.fn().mockResolvedValue(undefined),
	},
}))

const { api } = await import('$lib/api/client')
const { chat } = await import('$lib/stores/chat.svelte')
const { messages } = await import('$lib/stores/messages.svelte')
const { modals } = await import('$lib/stores/modals.svelte')
const ChatPropertiesModal = (await import('$lib/components/modals/ChatPropertiesModal.svelte'))
	.default

function participant(id: string, name: string, avatarUrl: string | null): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't1',
		access_level: 'editor',
		is_owner: id === 'user_me',
		kind: 'user',
		user: { id, username: name, display_name: name, avatar_url: avatarUrl },
	}
}

function agentParticipant(): Participant {
	return {
		id: 'part_agent_nova',
		thread_id: 't1',
		access_level: 'editor',
		is_owner: false,
		kind: 'agent',
		agent: { id: 'agent_nova', name: 'nova', profile_image_url: null },
		invoke_on_mention: null,
	}
}

function groupThread(): Thread {
	return {
		id: 't1',
		owner_id: 'user_me',
		title: 'weekend crew',
		tags: ['trip'],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [
			participant('user_me', 'me', null),
			participant('user_alice', 'alice', 'https://example.test/alice.png'),
			participant('user_bob', 'bob', 'https://example.test/bob.png'),
		],
	}
}

/** the agent joins last on purpose: the roster has to pull it to the front. */
function agentThread(): Thread {
	const thread = groupThread()
	thread.participants = [...(thread.participants ?? []), agentParticipant()]
	return thread
}

function open(thread: Thread = groupThread(), onClose: () => void = () => {}) {
	return render(ChatPropertiesModal, { props: { open: true, thread, onClose } })
}

function sectionOrder(): string[] {
	return [...screen.getByRole('dialog').querySelectorAll('section[data-section]')].map(
		(section) => section.getAttribute('data-section') ?? ''
	)
}

function rosterItems(): HTMLLIElement[] {
	const section = screen
		.getByRole('dialog')
		.querySelector<HTMLElement>('section[data-section="participants"]')
	return [...(section?.querySelectorAll<HTMLLIElement>('li') ?? [])]
}

/** rows are found by their name label, never by the badges printed beside it. */
function rosterItem(name: string): HTMLLIElement | null {
	return (
		rosterItems().find((item) =>
			[...item.querySelectorAll('span')].some(
				(span) => (span.textContent ?? '').trim() === name
			)
		) ?? null
	)
}

function badges(item: HTMLElement): string[] {
	return [...item.querySelectorAll('span')]
		.filter((span) => span.className.includes('rounded-pill'))
		.map((span) => (span.textContent ?? '').trim())
}

describe('ChatPropertiesModal', () => {
	afterEach(() => {
		auth.token = null
		messages.applyMuted('t1', false)
		chat.unreadCounts.clear()
		vi.clearAllMocks()
	})

	it('leads with the conversation faces and its name', () => {
		open()

		const header = screen
			.getByRole('dialog')
			.querySelector<HTMLElement>('header[data-identity]')
		expect(header).not.toBeNull()
		if (!header) return
		expect(within(header).getByAltText('alice')).toBeInTheDocument()
		expect(screen.getByLabelText('chat name')).toHaveValue('weekend crew')
	})

	it('groups the content into notifications, participants, tags and summary', () => {
		open()

		expect(sectionOrder()).toEqual([
			'notifications',
			'participants',
			'tags',
			'summary',
			'destructive',
		])
		expect(screen.getByText('3 participants')).toBeInTheDocument()
		expect(rosterItem('me')).not.toBeNull()
	})

	it('says owner, agent and you with badge pills rather than loose labels', () => {
		open(agentThread())

		const self = rosterItem('me')
		const nova = rosterItem('nova')
		expect(self).not.toBeNull()
		expect(nova).not.toBeNull()
		if (!self || !nova) return
		expect(badges(self)).toEqual(['owner', 'you'])
		expect(badges(nova)).toEqual(['agent'])
	})

	it('draws the row actions as pills, not as bare boxes', () => {
		open()

		const alice = rosterItem('alice')
		expect(alice).not.toBeNull()
		if (!alice) return
		const remove = within(alice).getByRole('button', { name: 'remove' })
		expect(remove.className).toContain('rounded-pill')
		expect(remove.className).toContain('text-red-500/70')
	})

	it('renames the chat itself, with no wiring from the caller', async () => {
		const onClose = vi.fn()
		open(groupThread(), onClose)

		const name = screen.getByLabelText('chat name')
		await fireEvent.input(name, { target: { value: 'ski trip' } })
		expect(name).toHaveValue('ski trip')

		const form = screen.getByRole('dialog').querySelector('form')
		expect(form).not.toBeNull()
		if (!form) return
		await fireEvent.submit(form)
		await vi.waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))

		expect(api.PATCH).toHaveBeenCalledWith(
			'/v1/threads/{thread_id}',
			expect.objectContaining({ body: { title: 'ski trip', tags: ['trip'] } })
		)
	})

	it('opens the share modal from the share tile', async () => {
		modals.close()
		open()

		await fireEvent.click(screen.getByRole('button', { name: 'share' }))

		expect(modals.active).toBe('resource-access')
		expect(modals.resourceAccessPayload).toEqual({
			resourceType: 'thread',
			resourceId: 't1',
			title: 'weekend crew',
		})
	})

	it('titles the destructive section and keeps it last, with archive out of it', () => {
		open()

		const order = sectionOrder()
		expect(order[order.length - 1]).toBe('destructive')

		const destructive = screen
			.getByRole('dialog')
			.querySelector<HTMLElement>('section[data-section="destructive"]')
		expect(destructive).not.toBeNull()
		if (!destructive) return
		expect(within(destructive).getByText('danger zone')).toBeInTheDocument()
		expect(within(destructive).getByText('delete chat')).toBeInTheDocument()
		expect(within(destructive).queryByText('archive')).toBeNull()
	})

	it('renders the destructive action as a pill, the way the confirm dialog does', () => {
		open()

		const remove = screen.getByRole('button', { name: 'delete chat' })
		expect(remove.className).toContain('rounded-pill')
	})

	it('archives from the action tiles, not from the destructive section', async () => {
		auth.token = userToken
		open()

		const archive = screen.getByRole('button', { name: 'archive' })
		expect(archive.closest('section[data-section="destructive"]')).toBeNull()

		await fireEvent.click(archive)

		await vi.waitFor(() =>
			expect(api.PATCH).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}',
				expect.objectContaining({ body: { archived: true } })
			)
		)
	})

	it('confirms before it deletes', async () => {
		modals.close()
		open()

		await fireEvent.click(screen.getByText('delete chat'))

		expect(modals.active).toBe('confirm-delete')
	})

	it('offers rename and delete only to a viewer whose access allows them', () => {
		const thread = groupThread()
		// a fresh id: the access store caches a level per resource for the run
		thread.id = 't_readonly'
		thread.owner_id = 'user_someone_else'
		open(thread)

		expect(screen.queryByLabelText('chat name')).toBeNull()
		// nothing destructive is left to offer, so the red section goes with it.
		expect(
			screen.getByRole('dialog').querySelector('section[data-section="destructive"]')
		).toBeNull()
		expect(screen.getByRole('button', { name: 'archive' })).toBeInTheDocument()
	})

	it('manages members in place, with no members tile and no second dialog', () => {
		open(agentThread())

		expect(screen.queryByRole('button', { name: 'members' })).toBeNull()
		expect(screen.queryByRole('dialog', { name: 'conversation' })).toBeNull()
		expect(screen.getAllByRole('dialog')).toHaveLength(1)
	})

	it('leads the roster with the agents, whatever order they joined in', () => {
		open(agentThread())

		expect(rosterItems()[0].textContent).toContain('nova')
		expect(screen.getByText('4 participants')).toBeInTheDocument()
	})

	it('keeps add members at the bottom of the list', () => {
		open(agentThread())

		const items = rosterItems()
		const addMembers = screen.getByRole('button', { name: 'add members' })
		expect(items[items.length - 1]).toContainElement(addMembers)
	})

	it('opens a proper picker modal from add members, never an inline field', async () => {
		open(agentThread())

		expect(screen.getAllByRole('dialog')).toHaveLength(1)

		await fireEvent.click(screen.getByRole('button', { name: 'add members' }))

		const dialogs = screen.getAllByRole('dialog')
		expect(dialogs).toHaveLength(2)
		expect(dialogs[1]).toHaveAttribute('aria-label', 'add members')
	})

	it('adds agents through the same picker, not through a dropdown', () => {
		open(agentThread())

		// the select-shaped "add an agent" control is gone; only the per-agent
		// mention-reply select is left in the roster.
		expect(screen.queryByRole('button', { name: 'add an agent' })).toBeNull()
		expect(screen.getByRole('button', { name: 'when nova is mentioned' })).toBeInTheDocument()
	})

	it('removes a member through the same participants route the panel used', async () => {
		open()

		const alice = rosterItem('alice')
		expect(alice).not.toBeNull()
		if (!alice) return
		await fireEvent.click(within(alice).getByRole('button', { name: 'remove' }))

		await vi.waitFor(() =>
			expect(api.DELETE).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}',
				{ params: { path: { thread_id: 't1', user_id: 'user_alice' } } }
			)
		)
	})

	it('offers the row actions only to a viewer whose access allows them', () => {
		const thread = agentThread()
		thread.id = 't_readonly_roster'
		thread.owner_id = 'user_someone_else'
		open(thread)

		const alice = rosterItem('alice')
		const nova = rosterItem('nova')
		const self = rosterItem('me')
		expect(alice).not.toBeNull()
		expect(nova).not.toBeNull()
		expect(self).not.toBeNull()
		if (!alice || !nova || !self) return
		// a reader takes nobody out of the chat, agents included, but may always
		// walk out themselves.
		expect(within(alice).queryByRole('button', { name: 'remove' })).toBeNull()
		expect(within(nova).queryByRole('button', { name: 'remove' })).toBeNull()
		expect(within(self).getByRole('button', { name: 'leave' })).toBeInTheDocument()
		expect(screen.queryByRole('button', { name: 'add members' })).toBeNull()
	})

	it('leaves the chat when the row is your own', async () => {
		const onClose = vi.fn()
		open(groupThread(), onClose)

		const self = rosterItem('me')
		expect(self).not.toBeNull()
		if (!self) return
		await fireEvent.click(within(self).getByRole('button', { name: 'leave' }))

		await vi.waitFor(() =>
			expect(api.DELETE).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}',
				{ params: { path: { thread_id: 't1', user_id: 'user_me' } } }
			)
		)
		expect(onClose).toHaveBeenCalled()
	})

	it('reflects the muted state and flips it through the same write the inbox uses', async () => {
		messages.applyMuted('t1', true)
		open()

		const mute = screen.getByRole('switch')
		expect(mute).toHaveAttribute('aria-checked', 'true')

		auth.token = userToken
		// the switch is a div that toggles on pointer or keyboard, never on click.
		await fireEvent.keyDown(mute, { key: 'Enter' })

		await vi.waitFor(() =>
			expect(api.PATCH).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}',
				expect.objectContaining({ body: { muted: false } })
			)
		)
	})

	it('mutes a chat that is not muted yet', async () => {
		auth.token = userToken
		open()

		const mute = screen.getByRole('switch')
		expect(mute).toHaveAttribute('aria-checked', 'false')

		await fireEvent.keyDown(mute, { key: 'Enter' })

		await vi.waitFor(() =>
			expect(api.PATCH).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}',
				expect.objectContaining({ body: { muted: true } })
			)
		)
	})

	it('marks the chat read from its tile, and offers it only while something is unread', async () => {
		chat.unreadCounts.set('t1', 3)
		auth.token = userToken
		open()

		const markRead = screen.getByRole('button', { name: 'mark as read' })
		expect(markRead).not.toBeDisabled()

		await fireEvent.click(markRead)

		await vi.waitFor(() =>
			expect(api.POST).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants/users/{user_id}/read',
				expect.objectContaining({
					params: { path: { thread_id: 't1', user_id: 'user_me' } },
				})
			)
		)
	})

	it('disables mark as read on a chat with nothing unread', () => {
		open()

		expect(screen.getByRole('button', { name: 'mark as read' })).toBeDisabled()
	})

	it('names the metadata action for what it writes', async () => {
		open()

		expect(await screen.findByRole('button', { name: 'generate info' })).toBeInTheDocument()
	})
})
