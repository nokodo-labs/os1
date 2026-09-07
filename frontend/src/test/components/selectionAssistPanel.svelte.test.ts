/**
 * the panel behind "ask" / "explain" on a selection.
 */

import { SelectionAssist } from '$lib/chat/selectionAssist.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { render, screen } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

// streamdown's math extension pulls in a stylesheet node cannot parse
vi.mock('$lib/components/markdown/MarkdownRenderer.svelte', async () => ({
	default: (await import('./MarkdownRendererStub.svelte')).default,
}))

import SelectionAssistPanel from '$lib/components/chat/SelectionAssistPanel.svelte'

const SELECTION = 'entropy never decreases in an isolated system'

function renderPanel(mode: 'ask' | 'explain', assist: SelectionAssist) {
	return render(SelectionAssistPanel, {
		props: {
			mode,
			selection: SELECTION,
			assist,
			onClose: vi.fn(),
			onAsk: vi.fn(),
		},
	})
}

describe('SelectionAssistPanel', () => {
	it('shows the selected text and an input in ask mode', () => {
		renderPanel('ask', new SelectionAssist())

		expect(screen.getByText(SELECTION)).toBeInTheDocument()
		expect(screen.getByLabelText('ask about the selected text')).toBeInTheDocument()
	})

	it('speaks the working state rather than showing a bare label', () => {
		const assist = new SelectionAssist()
		assist.phase = 'loading'
		const { container } = renderPanel('explain', assist)

		expect(screen.getByText('thinking')).toBeInTheDocument()
		expect(container.querySelector('.shimmer')).not.toBeNull()
	})

	it('offers copy on a finished answer and no retry', () => {
		const assist = new SelectionAssist()
		assist.phase = 'done'
		assist.answer = 'because energy spreads out'
		renderPanel('explain', assist)

		expect(screen.getByLabelText('copy message')).toBeInTheDocument()
		expect(screen.queryByText('retry')).not.toBeInTheDocument()
	})

	it('offers a retry when the run failed', async () => {
		// no agent selected: the run fails before it reaches the network
		selectedAgent.id = ''
		const assist = new SelectionAssist()
		await assist.run('explain this')
		renderPanel('explain', assist)

		expect(screen.getByText('no agent is selected')).toBeInTheDocument()
		expect(screen.getByText('retry')).toBeInTheDocument()
	})

	it('does not render the question input in explain mode', () => {
		renderPanel('explain', new SelectionAssist())

		expect(screen.queryByLabelText('ask about the selected text')).not.toBeInTheDocument()
	})
})
