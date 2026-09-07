/**
 * inline explain/ask: the run behind the selection popover.
 *
 * the two properties that matter here are that the run is thread-LESS (nothing
 * it produces can reach a transcript, a sidebar, or a durable failure record)
 * and that a run which delivered its answer finishes as a success.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

interface CapturedOptions {
	agentId: string
	threadId: string | null
	persist: boolean
	input: { type: string; content: { type: string; text: string }[] }
}

let captured: CapturedOptions | null = null
let scripted: unknown[] = []

vi.mock('$lib/api/streaming/chatStream', () => ({
	runChatStream: (opts: CapturedOptions) => {
		captured = opts
		return (async function* () {
			for (const event of scripted) yield event
		})()
	},
	resumeRunStream: vi.fn(),
	runCreateAndRunStream: vi.fn(),
	StreamHttpError: class StreamHttpError extends Error {},
}))

import { buildSelectionPrompt, SelectionAssist } from '$lib/chat/selectionAssist.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'

function chunk(text: string, done = false): unknown {
	return {
		event: 'delta',
		data: {
			run_id: 'run_1',
			agent_id: 'agent_1',
			message_id: 'msg_1',
			splice: null,
			delta: { chat: { message: { content: [{ type: 'text', text }] }, done } },
		},
	}
}

function failure(message: string): unknown {
	return { event: 'error', data: { message, run_id: 'run_1' } }
}

describe('selection assist runs', () => {
	beforeEach(() => {
		captured = null
		scripted = []
		selectedAgent.id = 'agent_1'
	})

	it('never binds the run to a thread', async () => {
		scripted = [chunk('an explanation', true)]
		const assist = new SelectionAssist()

		await assist.run(buildSelectionPrompt({ selection: 'quantum tunnelling' }))

		expect(captured?.threadId).toBeNull()
		expect(captured?.persist).toBe(false)
		expect(captured?.input.content[0].text).toContain('quantum tunnelling')
	})

	it('resolves cleanly when the answer finishes', async () => {
		scripted = [chunk('hello '), chunk('world', true)]
		const assist = new SelectionAssist()

		await assist.run('explain this')

		expect(assist.answer).toBe('hello world')
		expect(assist.phase).toBe('done')
		expect(assist.errorMessage).toBe('')
	})

	it('ends a finished run that tears itself down as a success', async () => {
		scripted = [chunk('the whole answer', true), failure('generation failed')]
		const assist = new SelectionAssist()

		await assist.run('explain this')

		expect(assist.phase).toBe('done')
		expect(assist.answer).toBe('the whole answer')
		expect(assist.errorMessage).toBe('')
	})

	it('still surfaces a failure that interrupts the answer', async () => {
		scripted = [chunk('half an ans'), failure('generation failed')]
		const assist = new SelectionAssist()

		await assist.run('explain this')

		expect(assist.phase).toBe('error')
		expect(assist.errorMessage).toBe('generation failed')
		expect(assist.canRetry).toBe(true)
		// the partial stays on screen next to the failure
		expect(assist.answer).toBe('half an ans')
	})

	it('treats a run that said nothing as a failure', async () => {
		scripted = []
		const assist = new SelectionAssist()

		await assist.run('explain this')

		expect(assist.phase).toBe('error')
		expect(assist.errorMessage).toBe('no answer came back')
	})

	it('reports a missing agent instead of starting a run', async () => {
		selectedAgent.id = ''
		const assist = new SelectionAssist()

		await assist.run('explain this')

		expect(captured).toBeNull()
		expect(assist.phase).toBe('error')
		expect(assist.errorMessage).toBe('no agent is selected')
	})
})

describe('selection prompts', () => {
	it('quotes the selection and carries the passage it came from', () => {
		const prompt = buildSelectionPrompt({
			selection: 'the second law',
			context: 'entropy is the subject of the second law of thermodynamics',
		})

		expect(prompt).toContain('explain this clearly and concisely')
		expect(prompt).toContain('the second law')
		expect(prompt).toContain('entropy is the subject')
	})

	it('carries the previous answer into a follow-up', () => {
		const prompt = buildSelectionPrompt({
			selection: 'the second law',
			question: 'why does it matter?',
			previousAnswer: 'it is about entropy',
		})

		expect(prompt).toContain('regarding the following text: "the second law"')
		expect(prompt).toContain('why does it matter?')
		expect(prompt).toContain('it is about entropy')
	})
})
