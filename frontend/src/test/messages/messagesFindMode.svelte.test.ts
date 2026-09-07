/**
 * the messages home in find mode (F106, the first F36 instance): the chat input
 * docked at the bottom of the page in both layout modes, results replacing the
 * inbox above it, and the inbox back the moment the query goes away.
 */

import type { components } from '$lib/api/types'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
type Participant = NonNullable<Conversation['participants']>[number]

function participant(id: string, name: string): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't',
		access_level: 'editor',
		is_owner: false,
		kind: 'user',
		user: { id, username: name, display_name: name },
	}
}

function conversation(id: string, other: string): Conversation {
	return {
		id,
		owner_id: 'user_me',
		title: null,
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [participant('user_me', 'me'), participant(`user_${other}`, other)],
	}
}

const alice = conversation('t_alice', 'alice')
const bob = conversation('t_bob', 'bob')

const mocks = vi.hoisted(() => ({
	goto: vi.fn(),
	device: { isMobile: false, isTouch: false, virtualKeyboardOpen: false },
	messages: {
		conversations: [] as Conversation[],
		invites: [] as Conversation[],
		isLoading: false,
		isLoadingMore: false,
		hasMore: false,
		hasLoaded: true,
		hasLoadedInvites: true,
		inviteCount: 0,
		unreadCount: () => 0,
		isMuted: () => false,
		load: vi.fn(),
		loadMore: vi.fn(),
		loadInvites: vi.fn(),
		removeConversation: vi.fn(),
		applyMuted: vi.fn(),
	},
}))

vi.mock('$app/environment', () => ({ browser: false, dev: false }))
vi.mock('$app/navigation', () => ({
	goto: mocks.goto,
	onNavigate: vi.fn(),
	afterNavigate: vi.fn(),
	beforeNavigate: vi.fn(),
}))
vi.mock('$app/paths', () => ({
	base: '',
	assets: '',
	resolve: (path: string) => path,
	asset: (path: string) => path,
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: { items: [] }, error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => 'token'),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUserId: 'user_me' },
}))

vi.mock('$lib/stores/device.svelte', () => ({
	device: mocks.device,
	DEVICE_MOBILE_BREAKPOINT_PX: 888,
}))

vi.mock('$lib/stores/messages.svelte', () => ({ messages: mocks.messages }))

vi.mock('$lib/contexts/systemChromeContext.svelte', () => ({
	useSystemChrome: () => ({
		setContextActions: vi.fn(),
		isDockOpen: false,
		layout: { leftWidthClass: null },
	}),
}))

const MessagesPage = (await import('../../routes/messages/+page.svelte')).default

async function type(value: string): Promise<void> {
	await fireEvent.input(screen.getByRole('textbox'), { target: { value } })
	await tick()
	await tick()
}

beforeEach(() => {
	mocks.goto.mockReset()
	mocks.device.isMobile = false
	mocks.messages.conversations = [alice, bob]
	mocks.messages.invites = []
})

describe('messages find mode', () => {
	it('docks the search bar at the bottom of the page in both layout modes', async () => {
		for (const isMobile of [false, true]) {
			mocks.device.isMobile = isMobile
			const { container, unmount } = render(MessagesPage)
			await tick()

			const bar = container.querySelector('[data-messages-search-bar]')
			expect(bar).not.toBeNull()
			expect(bar?.className).toContain('bottom-0')
			expect(bar?.querySelector('textarea')).not.toBeNull()
			// a find bar, never a composer
			expect(bar?.querySelector('[aria-label="send message"]')).toBeNull()
			expect(screen.getByLabelText('search')).toBeInTheDocument()

			unmount()
		}
	})

	it('replaces the inbox with the shared results box while a query stands', async () => {
		const { container } = render(MessagesPage)
		await tick()
		expect(container.querySelector('[data-conversation-card]')).not.toBeNull()

		await type('alice')

		expect(container.querySelector('[data-search-results]')).not.toBeNull()
		expect(container.querySelector('[data-conversation-card]')).toBeNull()
		expect(container.querySelectorAll('[data-row]')).toHaveLength(1)
		expect(screen.getByText('alice')).toBeInTheDocument()
	})

	it('opens the thread the picked row stands for', async () => {
		const { container } = render(MessagesPage)
		await tick()
		await type('alice')

		const row = container.querySelector('[data-row] [role="button"]')
		if (!row) throw new Error('no result row')
		await fireEvent.click(row)

		expect(mocks.goto).toHaveBeenCalledWith('/c/t_alice')
	})

	it('gives the inbox back on escape', async () => {
		const { container } = render(MessagesPage)
		await tick()
		await type('alice')
		expect(container.querySelector('[data-search-results]')).not.toBeNull()

		await fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' })
		await tick()

		expect(container.querySelector('[data-search-results]')).toBeNull()
		expect(container.querySelector('[data-conversation-card]')).not.toBeNull()
	})

	it('gives the inbox back on an empty query', async () => {
		const { container } = render(MessagesPage)
		await tick()
		await type('alice')

		await type('')

		expect(container.querySelector('[data-search-results]')).toBeNull()
		expect(container.querySelectorAll('[data-row]')).toHaveLength(2)
	})

	it('lists matching requests as their own run, which opens the requests view', async () => {
		mocks.messages.invites = [conversation('t_carol', 'carol')]
		mocks.messages.inviteCount = 1
		const { container } = render(MessagesPage)
		await tick()

		await type('carol')

		const labels = [...container.querySelectorAll('[data-section-label]')].map((el) =>
			el.textContent?.trim()
		)
		expect(labels).toEqual(['requests'])
		mocks.messages.inviteCount = 0
	})
})
