/**
 * the messages inbox row: the preview line under the conversation title, which
 * names who spoke last and what they said.
 */

import type { components } from '$lib/api/types'
import { render } from '@testing-library/svelte'
import { SvelteMap } from 'svelte/reactivity'
import { afterEach, describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
type Message = components['schemas']['Message']
type Participant = NonNullable<Conversation['participants']>[number]

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

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

const ConversationRow = (await import('$lib/components/messages/ConversationRow.svelte')).default
const { chat } = await import('$lib/stores/chat.svelte')

/** put people into the store's live composing map, the way a WS signal does. */
function setComposing(threadId: string, userIds: string[]): void {
	const composers = new SvelteMap<string, number>()
	for (const userId of userIds) composers.set(userId, Date.now() + 8000)
	chat.composingUsers.set(threadId, composers)
}

function participant(id: string, username: string, displayName: string): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't1',
		access_level: 'editor',
		is_owner: false,
		kind: 'user',
		user: { id, username, display_name: displayName },
	}
}

function message(overrides: Partial<Message>): Message {
	return {
		id: 'msg_1',
		thread_id: 't1',
		type: 'user',
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		...overrides,
	}
}

function conversation(lastMessage: Message | null): Conversation {
	return {
		id: 't1',
		owner_id: 'user_me',
		title: 'alice',
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [
			{ ...participant('user_me', 'me', 'me'), is_owner: true },
			participant('user_alice', 'alice', 'alice'),
		],
		last_message: lastMessage,
	}
}

function previewOf(thread: Conversation, unreadCount = 0): HTMLElement | null {
	const { container } = render(ConversationRow, {
		props: { thread, unreadCount, onOpen: () => {}, onRemoved: () => {} },
	})
	return container.querySelector<HTMLElement>('[data-preview]')
}

describe('ConversationRow preview', () => {
	it('shows only the text in a direct thread', () => {
		const thread = conversation(
			message({
				sender_user_id: 'user_alice',
				content: [{ type: 'text', text: 'dinner at eight?' }],
			})
		)

		expect(previewOf(thread)?.textContent?.trim()).toBe('dinner at eight?')
	})

	it('names the sender before the text in a group thread', () => {
		const thread = conversation(
			message({
				sender_user_id: 'user_alice',
				content: [{ type: 'text', text: 'dinner at eight?' }],
			})
		)
		thread.participants = [
			...(thread.participants ?? []),
			participant('user_bob', 'bob', 'bob'),
		]

		expect(previewOf(thread)?.textContent?.trim()).toBe('alice: dinner at eight?')
	})

	it('calls the current user "you" in a group thread', () => {
		const thread = conversation(
			message({ sender_user_id: 'user_me', content: [{ type: 'text', text: 'on my way' }] })
		)

		thread.participants = [
			...(thread.participants ?? []),
			participant('user_bob', 'bob', 'bob'),
		]

		expect(previewOf(thread)?.textContent?.trim()).toBe('you: on my way')
	})

	it('labels a message that carries no text', () => {
		const thread = conversation(
			message({
				sender_user_id: 'user_alice',
				content: [{ type: 'image', url: 'https://example.test/cat.png' }],
			})
		)

		expect(previewOf(thread)?.textContent?.trim()).toBe('photo')
	})

	it('keeps the participants line when the thread has no messages', () => {
		expect(previewOf(conversation(null))?.textContent?.trim()).toBe('@alice')
	})

	afterEach(() => {
		chat.composingUsers.clear()
	})

	it('says somebody is typing instead of the last message', () => {
		const thread = conversation(
			message({ sender_user_id: 'user_alice', content: [{ type: 'text', text: 'hi' }] })
		)
		setComposing(thread.id, ['user_alice'])

		expect(previewOf(thread)?.textContent?.trim()).toBe('typing...')
	})

	it('names who is typing in a group thread', () => {
		const thread = conversation(null)
		thread.participants = [
			...(thread.participants ?? []),
			participant('user_bob', 'bob', 'bob'),
		]
		setComposing(thread.id, ['user_alice'])

		expect(previewOf(thread)?.textContent?.trim()).toBe('alice is typing...')

		setComposing(thread.id, ['user_alice', 'user_bob'])
		expect(previewOf(thread)?.textContent?.trim()).toBe('2 people are typing...')
	})

	it('keeps the last message when only you are composing', () => {
		const thread = conversation(
			message({ sender_user_id: 'user_alice', content: [{ type: 'text', text: 'hi' }] })
		)
		setComposing(thread.id, ['user_me'])

		expect(previewOf(thread)?.textContent?.trim()).toBe('hi')
	})

	it('strengthens the line while the row is unread', () => {
		const thread = conversation(
			message({ sender_user_id: 'user_alice', content: [{ type: 'text', text: 'hi' }] })
		)

		expect(previewOf(thread, 3)?.className).toContain('font-medium')
		expect(previewOf(thread)?.className).not.toContain('font-medium')
	})
})
