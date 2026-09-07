/**
 * the messages inbox card: one background around a whole run of rows, headed
 * by its group name, with the row menu overlaid rather than given space.
 */

import type { components } from '$lib/api/types'
import { render } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

type Conversation = components['schemas']['Thread']
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

const ConversationSection = (await import('$lib/components/messages/ConversationSection.svelte'))
	.default

function participant(id: string): Participant {
	return {
		id: `part_${id}`,
		thread_id: 't',
		access_level: 'editor',
		is_owner: false,
		kind: 'user',
		user: { id, username: id, display_name: id },
	}
}

function conversation(id: string): Conversation {
	return {
		id,
		owner_id: 'user_me',
		title: id,
		tags: [],
		is_temporary: false,
		created_at: '2026-01-01T00:00:00Z',
		updated_at: '2026-01-01T00:00:00Z',
		last_activity_at: '2026-01-01T00:00:00Z',
		participants: [participant('user_me'), participant('user_alice')],
	}
}

function renderSection(label?: string) {
	return render(ConversationSection, {
		props: {
			label,
			threads: [conversation('t1'), conversation('t2')],
			unreadCountOf: () => 0,
			onOpen: () => {},
			onRemoved: () => {},
		},
	})
}

describe('ConversationSection', () => {
	it('wraps the whole run of rows in one card under its header', () => {
		const { container } = renderSection('unread')

		expect(container.querySelectorAll('[data-conversation-card]')).toHaveLength(1)
		expect(container.querySelector('[data-card-label]')?.textContent?.trim()).toBe('unread')
		expect(container.querySelectorAll('[data-row]')).toHaveLength(2)
	})

	it('leaves the header out when the card is not a group', () => {
		const { container } = renderSection()

		expect(container.querySelector('[data-card-label]')).toBeNull()
		expect(container.querySelector('[data-conversation-card]')).not.toBeNull()
	})

	it('draws a hairline above every row but the first', () => {
		const { container } = renderSection('unread')
		const rows = [...container.querySelectorAll('[data-row]')]

		expect(rows[0].querySelector('[aria-hidden="true"].h-px')).toBeNull()
		expect(rows[1].querySelector('[aria-hidden="true"].h-px')).not.toBeNull()
	})

	it('keeps the row menu out of the layout flow in pointer mode', () => {
		const { container } = renderSection('unread')
		const row = container.querySelector('[data-row]')
		const actions = row?.querySelector('[data-row-actions]')
		const rowButton = row?.querySelector('[role="button"]')

		expect(actions?.className).toContain('absolute')
		expect(actions?.className).toContain('opacity-0')
		expect(actions?.className).toContain('group-hover/row:opacity-100')
		// the row content reserves no room for it, and does not nest it either
		expect(rowButton?.className).toContain('pr-3')
		expect(rowButton?.className).not.toContain('pr-14')
		expect(rowButton?.querySelector('[data-row-actions]')).toBeNull()
	})
})
