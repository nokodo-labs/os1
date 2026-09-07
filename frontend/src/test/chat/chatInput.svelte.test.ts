import type { MessageAuthor } from '$lib/chat/participants'
import type { RunModifiers } from '$lib/chat/types'
import ChatInput from '$lib/components/chat/ChatInput.svelte'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

const ada: MessageAuthor = { id: 'agent_7', name: 'ada', avatarUrl: null, isAgent: true }

function mount(props: {
	onSubmit?: (message: string, modifiers?: RunModifiers) => void
	onArmAgent?: (agentId: string | null) => void
	invokableAgents?: MessageAuthor[]
	armedAgentId?: string | null
}) {
	return render(ChatInput, { props: { value: 'hello', ...props } })
}

describe('ChatInput invocation', () => {
	it('sends plain when nothing is armed, even with invokable agents', () => {
		const onSubmit = vi.fn()
		mount({ onSubmit, invokableAgents: [ada] })

		screen.getByLabelText('send message').click()

		expect(onSubmit).toHaveBeenCalledTimes(1)
		expect(onSubmit.mock.calls[0][1]).toBeUndefined()
	})

	it('carries the armed agent in the submit modifiers and releases the arming', () => {
		const onSubmit = vi.fn()
		const onArmAgent = vi.fn()
		mount({ onSubmit, onArmAgent, invokableAgents: [ada], armedAgentId: ada.id })

		screen.getByLabelText('send and invoke ada').click()

		expect(onSubmit).toHaveBeenCalledWith(
			'hello',
			expect.objectContaining({ invokeAgentId: 'agent_7' })
		)
		expect(onArmAgent).toHaveBeenCalledWith(null)
	})

	it('opens the agent list on ctrl+enter when nothing is armed', async () => {
		const onSubmit = vi.fn()
		mount({ onSubmit, invokableAgents: [ada] })

		await fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter', ctrlKey: true })

		expect(onSubmit).not.toHaveBeenCalled()
		expect(screen.getByRole('menuitem', { name: /ada/ })).toBeInTheDocument()
	})

	it('offers no invocation affordance without invokable agents', () => {
		mount({ onSubmit: vi.fn() })

		expect(screen.queryByLabelText('send and invoke an agent')).toBeNull()
	})
})
