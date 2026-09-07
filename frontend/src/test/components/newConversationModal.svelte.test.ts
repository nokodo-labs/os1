/**
 * the new-conversation modal: picking people is the whole interaction, so the
 * pick has to register and the start button has to carry it into a thread.
 */

import { cleanup, fireEvent, render } from '@testing-library/svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

interface Row {
	id: string
	username: string
	display_name: string
	avatar_url: string | null
}

const state = vi.hoisted(() => ({
	friends: [] as Row[],
	createdThread: null as { id: string } | null,
}))

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUserId: 'user_me' },
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

vi.mock('$lib/stores/messages.svelte', () => ({
	messages: {
		createThread: vi.fn(async () => state.createdThread),
	},
}))

vi.mock('$lib/stores/notifications.svelte', () => ({
	showError: vi.fn(),
}))

const { goto } = await import('$app/navigation')
const { messages } = await import('$lib/stores/messages.svelte')
const NewConversationModal = (await import('$lib/components/messages/NewConversationModal.svelte'))
	.default

function person(id: string, name: string): Row {
	return { id, username: name, display_name: name, avatar_url: null }
}

function buttons(): HTMLButtonElement[] {
	return [...document.body.querySelectorAll('button')]
}

function text(node: Element): string {
	return (node.textContent ?? '').replace(/\s+/g, ' ').trim()
}

/** the row for one candidate, found by the handle it prints under the name. */
function candidateRow(handle: string): HTMLButtonElement {
	const row = buttons().find((button) => text(button).includes(`@${handle}`))
	expect(row).toBeDefined()
	if (!row) throw new Error(`no candidate row for @${handle}`)
	return row
}

/** the chip a pick puts above the list, which is how a pick shows itself. */
function chip(name: string): HTMLButtonElement | undefined {
	return buttons().find((button) => text(button) === `${name} ×`)
}

function startButton(): HTMLButtonElement {
	const button = buttons().find((candidate) =>
		['message', 'start group', 'starting'].includes(text(candidate))
	)
	expect(button).toBeDefined()
	if (!button) throw new Error('no start button')
	return button
}

function open(): { onClose: ReturnType<typeof vi.fn> } {
	const onClose = vi.fn()
	render(NewConversationModal, { props: { open: true, onClose } })
	return { onClose }
}

describe('new conversation modal', () => {
	beforeEach(() => {
		cleanup()
		vi.clearAllMocks()
		state.friends = [person('user_alice', 'alice'), person('user_bob', 'bob')]
		state.createdThread = { id: 't_new' }
	})

	it('registers a click on a person as a pick', async () => {
		open()
		expect(chip('alice')).toBeUndefined()
		expect(startButton().disabled).toBe(true)

		await fireEvent.click(candidateRow('alice'))

		expect(chip('alice')).toBeDefined()
		expect(startButton().disabled).toBe(false)
	})

	it('takes a picked person into their thread', async () => {
		const { onClose } = open()
		await fireEvent.click(candidateRow('alice'))
		await fireEvent.click(startButton())

		expect(messages.createThread).toHaveBeenCalledWith({ member_user_ids: ['user_alice'] })
		expect(onClose).toHaveBeenCalled()
		expect(goto).toHaveBeenCalledWith('/c/t_new')
	})

	it('turns a second pick into a group', async () => {
		open()
		await fireEvent.click(candidateRow('alice'))
		await fireEvent.click(candidateRow('bob'))

		expect(text(startButton())).toBe('start group')

		await fireEvent.click(startButton())
		expect(messages.createThread).toHaveBeenCalledWith({
			member_user_ids: ['user_alice', 'user_bob'],
		})
	})

	it('lets a second click take a pick back', async () => {
		open()
		await fireEvent.click(candidateRow('alice'))
		await fireEvent.click(candidateRow('alice'))

		expect(chip('alice')).toBeUndefined()
		expect(startButton().disabled).toBe(true)
	})
})
