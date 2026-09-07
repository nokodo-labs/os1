/**
 * the island's conversation identity: the faces and name that stand in for the
 * chat itself, and the tap that opens its info modal.
 */

import ConversationIdentity from '$lib/components/chat/ConversationIdentity.svelte'
import type { ConversationDisplay } from '$lib/utils/conversationDisplay'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

function directDisplay(): ConversationDisplay {
	return {
		title: 'alice',
		subtitle: '@alice',
		faces: [
			{
				id: 'user_alice',
				label: 'alice',
				avatarUrl: 'https://example.test/alice.png',
				isAgent: false,
			},
		],
		humanCount: 2,
		isGroup: false,
	}
}

function groupDisplay(): ConversationDisplay {
	return {
		title: 'weekend crew',
		subtitle: 'alice, bob',
		faces: [
			{
				id: 'user_alice',
				label: 'alice',
				avatarUrl: 'https://example.test/alice.png',
				isAgent: false,
			},
			{ id: 'user_bob', label: 'bob', avatarUrl: null, isAgent: false },
		],
		humanCount: 3,
		isGroup: true,
	}
}

describe('ConversationIdentity', () => {
	it('renders the conversation face beside its name', () => {
		render(ConversationIdentity, { props: { display: directDisplay(), onOpen: () => {} } })

		expect(screen.getByAltText('alice')).toBeInTheDocument()
		expect(screen.getByRole('button', { name: 'chat info' }).textContent).toContain('alice')
	})

	it('keeps a direct chat to a single line', () => {
		render(ConversationIdentity, { props: { display: directDisplay(), onOpen: () => {} } })

		expect(screen.getByRole('button', { name: 'chat info' }).textContent).not.toContain(
			'people'
		)
	})

	it('counts the members of a group under its name', () => {
		render(ConversationIdentity, { props: { display: groupDisplay(), onOpen: () => {} } })

		expect(screen.getByText('3 people')).toBeInTheDocument()
	})

	it('opens the info modal when tapped', async () => {
		const onOpen = vi.fn()
		render(ConversationIdentity, { props: { display: groupDisplay(), onOpen } })

		await fireEvent.click(screen.getByRole('button', { name: 'chat info' }))

		expect(onOpen).toHaveBeenCalledTimes(1)
	})
})
