/**
 * the one picker behind "add members" and "add agents": both halves have to
 * search, multi-select, gate the confirm on a pick, and write through the same
 * participants route.
 */

import type { components } from '$lib/api/types'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type Thread = components['schemas']['Thread']

interface AgentRow {
	id: string
	name: string
	description: string | null
	profile_image_url: string | null
}

interface FriendRow {
	id: string
	username: string
	display_name: string
	avatar_url: string | null
}

const state = vi.hoisted(() => ({
	agents: [] as AgentRow[],
	friends: [] as FriendRow[],
}))

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

vi.mock('$app/state', () => ({ page: { url: new URL('https://nokodo.test/messages') } }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: [], error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUserId: 'user_me' },
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: {
		get list() {
			return state.agents
		},
		load: vi.fn().mockResolvedValue(undefined),
	},
}))

vi.mock('$lib/stores/friends.svelte', () => ({
	friends: {
		get list() {
			return state.friends
		},
		load: vi.fn().mockResolvedValue(undefined),
		searchUsers: vi.fn().mockResolvedValue([]),
	},
}))

vi.mock('$lib/stores/notifications.svelte', () => ({ showError: vi.fn() }))

const { api } = await import('$lib/api/client')
const ThreadAddParticipantsModal = (
	await import('$lib/components/modals/ThreadAddParticipantsModal.svelte')
).default

function thread(): Thread {
	return {
		id: 't1',
		owner_id: 'user_me',
		title: 'weekend crew',
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [],
	}
}

function open(kind: 'members' | 'agents', excludeIds: string[] = []): void {
	render(ThreadAddParticipantsModal, {
		props: { open: true, thread: thread(), kind, excludeIds, onClose: () => {} },
	})
}

function rows(): HTMLButtonElement[] {
	const list = screen.getByRole('dialog').querySelector('.max-h-72')
	return [...(list?.querySelectorAll('button') ?? [])]
}

function rowNames(): string[] {
	return rows().map((row) => (row.querySelector('span')?.textContent ?? '').trim())
}

function addButton(): HTMLButtonElement {
	const button = screen.getByRole('button', { name: 'add' })
	if (!(button instanceof HTMLButtonElement)) throw new Error('no add button')
	return button
}

describe('ThreadAddParticipantsModal', () => {
	beforeEach(() => {
		vi.clearAllMocks()
		state.agents = [
			{ id: 'agent_nova', name: 'nova', description: 'the writer', profile_image_url: null },
			{
				id: 'agent_atlas',
				name: 'atlas',
				description: 'the planner',
				profile_image_url: null,
			},
			{ id: 'agent_iris', name: 'iris', description: null, profile_image_url: null },
		]
		state.friends = [
			{ id: 'user_alice', username: 'alice', display_name: 'alice', avatar_url: null },
			{ id: 'user_bob', username: 'bob', display_name: 'bob', avatar_url: null },
		]
	})

	it('gives the agent picker a search field and rows, not a select', () => {
		open('agents')

		expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'add agents')
		expect(screen.getByLabelText('search agents')).toBeInTheDocument()
		expect(rowNames()).toEqual(['nova', 'atlas', 'iris'])
	})

	it('filters agents by name or by what they do', async () => {
		open('agents')

		await fireEvent.input(screen.getByLabelText('search agents'), {
			target: { value: 'plan' },
		})

		expect(rowNames()).toEqual(['atlas'])
	})

	it('never offers an agent already in the chat', () => {
		open('agents', ['agent_nova'])

		expect(rowNames()).toEqual(['atlas', 'iris'])
	})

	it('gates the confirm on a pick and writes the picked agents', async () => {
		open('agents')
		expect(addButton()).toBeDisabled()

		await fireEvent.click(rows()[0])
		await fireEvent.click(rows()[1])
		expect(addButton()).not.toBeDisabled()

		await fireEvent.click(addButton())

		await vi.waitFor(() =>
			expect(api.POST).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants',
				expect.objectContaining({ body: { agent_ids: ['agent_nova', 'agent_atlas'] } })
			)
		)
	})

	it('offers friends up front in the member picker and adds them by id', async () => {
		open('members')

		expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'add members')
		expect(rowNames()).toEqual(['alice', 'bob'])

		await fireEvent.click(rows()[0])
		await fireEvent.click(addButton())

		await vi.waitFor(() =>
			expect(api.POST).toHaveBeenCalledWith(
				'/v1/threads/{thread_id}/participants',
				expect.objectContaining({ body: { user_ids: ['user_alice'] } })
			)
		)
	})

	it('takes a pick back on a second click', async () => {
		open('members')

		await fireEvent.click(rows()[0])
		expect(addButton()).not.toBeDisabled()

		await fireEvent.click(rows()[0])
		expect(addButton()).toBeDisabled()
	})
})
