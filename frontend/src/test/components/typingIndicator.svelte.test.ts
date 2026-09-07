/**
 * the typing bubble at the bottom of a transcript: one bubble, a face per
 * composer, and a label that names them for a screen reader.
 */

import TypingIndicator from '$lib/components/chat/TypingIndicator.svelte'
import type { ConversationFace } from '$lib/utils/conversationDisplay'
import { render } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

function face(id: string, label: string, avatarUrl: string | null = null): ConversationFace {
	return { id, label, avatarUrl, isAgent: false }
}

function renderIndicator(composers: ConversationFace[], showFaces = true): HTMLElement {
	const { container } = render(TypingIndicator, { props: { composers, showFaces } })
	return container
}

describe('TypingIndicator', () => {
	it('renders nothing while nobody is composing', () => {
		expect(renderIndicator([]).querySelector('[data-typing-indicator]')).toBeNull()
	})

	it('shows one bubble and the composer face', () => {
		const container = renderIndicator([face('user_ada', 'Ada')])
		const indicator = container.querySelector('[data-typing-indicator]')

		expect(indicator).not.toBeNull()
		expect(indicator?.getAttribute('aria-label')).toBe('Ada is typing')
		expect(container.querySelectorAll('.typing-dot')).toHaveLength(3)
		expect(container.textContent).toContain('A')
	})

	it('uses the composer avatar when they have one', () => {
		const container = renderIndicator([face('user_ada', 'Ada', 'https://example.test/ada.png')])

		expect(container.querySelector('img')?.getAttribute('alt')).toBe('Ada')
	})

	it('stacks faces behind a single bubble when several compose', () => {
		const container = renderIndicator([face('user_ada', 'Ada'), face('user_bob', 'Bob')])

		expect(container.querySelectorAll('.typing-dots')).toHaveLength(1)
		expect(container.querySelectorAll('.size-8')).toHaveLength(2)
		expect(container.querySelector('[data-typing-indicator]')?.getAttribute('aria-label')).toBe(
			'Ada and Bob are typing'
		)
	})

	it('drops the face in a DM: the bubble alone is already that person', () => {
		const container = renderIndicator(
			[face('user_ada', 'Ada', 'https://example.test/ada.png')],
			false
		)
		const indicator = container.querySelector('[data-typing-indicator]')

		expect(indicator).not.toBeNull()
		expect(container.querySelectorAll('.typing-dots')).toHaveLength(1)
		expect(container.querySelectorAll('.size-8')).toHaveLength(0)
		expect(container.querySelector('img')).toBeNull()
		// the screen reader still hears who it is
		expect(indicator?.getAttribute('aria-label')).toBe('Ada is typing')
	})

	it('caps the stack and counts the rest in the label', () => {
		const container = renderIndicator([
			face('user_ada', 'Ada'),
			face('user_bob', 'Bob'),
			face('user_cal', 'Cal'),
			face('user_dee', 'Dee'),
		])

		expect(container.querySelectorAll('.typing-dots')).toHaveLength(1)
		expect(container.querySelector('[data-typing-indicator]')?.getAttribute('aria-label')).toBe(
			'Ada, Bob and 2 others are typing'
		)
		// the faces past the cap are counted in the label, not crowded into the stack
		expect(container.querySelectorAll('.size-8')).toHaveLength(3)
	})
})
