/**
 * the centered system row: quiet text, no bubble, names carrying the weight.
 */

import type { SystemRowSegment } from '$lib/chat/systemEvents'
import ChatSystemRow from '$lib/components/chat/ChatSystemRow.svelte'
import { render } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

function renderRow(segments: SystemRowSegment[], header = false): HTMLElement {
	const { container } = render(ChatSystemRow, { props: { segments, header } })
	return container
}

describe('ChatSystemRow', () => {
	it('renders nothing when there is nothing to say', () => {
		expect(renderRow([]).querySelector('[data-chat-system-row]')).toBeNull()
	})

	it('reads as one sentence and labels itself for a screen reader', () => {
		const container = renderRow([
			{ text: 'alice', strong: true },
			{ text: ' added ' },
			{ text: 'bob', strong: true },
			{ text: ' to this chat' },
		])
		const row = container.querySelector('[data-chat-system-row]')

		expect(row?.textContent?.replace(/\s+/g, ' ').trim()).toBe('alice added bob to this chat')
		expect(row?.getAttribute('aria-label')).toBe('alice added bob to this chat')
	})

	it('is quiet and centered, never a bubble', () => {
		const row = renderRow([{ text: 'bob left the chat' }]).querySelector(
			'[data-chat-system-row]'
		)
		const paragraph = row?.querySelector('p')

		expect(row?.className).toContain('justify-center')
		expect(paragraph?.className).toContain('text-foreground/45')
		expect(paragraph?.className).toContain('text-xs')
		expect(paragraph?.className).toContain('text-center')
	})

	it('gives the names inside the sentence a little more weight', () => {
		const container = renderRow([{ text: 'alice', strong: true }, { text: ' left the chat' }])
		const spans = container.querySelectorAll('p > span')

		expect(spans[0].className).toContain('font-medium')
		expect(spans[1].className).toBe('')
	})

	it('opens the transcript without the punctuating row spacing', () => {
		const header = renderRow([{ text: 'this is the beginning' }], true).querySelector(
			'[data-chat-system-row]'
		)
		const row = renderRow([{ text: 'bob left the chat' }]).querySelector(
			'[data-chat-system-row]'
		)

		expect(header?.className).toContain('pb-1')
		expect(row?.className).toContain('py-1')
	})
})
