/**
 * inline explain/ask - the run behind the text-selection popover.
 *
 * the answer belongs to the popover and to nothing else, so the run is
 * deliberately thread-LESS. a `persist=false` run that still names a thread is
 * a thread-bound run everywhere it matters: the backend announces it with
 * `run.started` to every session that can read the thread (which resumes its
 * stream and renders the answer as a message), and a failed one writes a
 * DURABLE `run.error` into the conversation. without a thread_id the same
 * inference happens and nobody is told.
 */

import { runChatStream } from '$lib/api/streaming'
import { sdkPartsToText } from '$lib/chat/helpers'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'

export type SelectionAssistPhase = 'idle' | 'loading' | 'thinking' | 'streaming' | 'done' | 'error'

/** how much of a surrounding passage travels with the question. */
const CONTEXT_LIMIT = 1600

export interface SelectionPromptInput {
	/** the text the reader highlighted. */
	selection: string
	/** the passage the selection was taken from, when it adds anything. */
	context?: string | null
	/** what to ask about it; omitted for the one-tap explain. */
	question?: string | null
	/** the answer a follow-up is following up on. */
	previousAnswer?: string | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null
}

function clip(text: string): string {
	const trimmed = text.trim()
	return trimmed.length > CONTEXT_LIMIT ? `${trimmed.slice(0, CONTEXT_LIMIT)}...` : trimmed
}

/**
 * build the prompt for one selection question.
 *
 * a thread-less run reads nothing on its own, so everything it may need has to
 * be in the prompt: the selection, the passage it came from, and - on a
 * follow-up - the answer being followed up on.
 */
export function buildSelectionPrompt(input: SelectionPromptInput): string {
	const selection = input.selection.trim()
	const question = input.question?.trim() ?? ''
	const parts = [
		question
			? `regarding the following text: "${selection}"\n\n${question}`
			: `explain this clearly and concisely:\n\n${selection}`,
	]
	const context = input.context ? clip(input.context) : ''
	if (context && context !== selection) {
		parts.push(`for context, the passage it appears in:\n\n${context}`)
	}
	const previous = input.previousAnswer ? clip(input.previousAnswer) : ''
	if (previous) parts.push(`your previous answer was:\n\n${previous}`)
	return parts.join('\n\n')
}

interface ParsedDelta {
	text: string
	hasTool: boolean
	finished: boolean
}

/** the streamed text lives at `delta.chat.message.content`, never at `delta.content`. */
function parseDelta(raw: unknown): ParsedDelta {
	if (!isRecord(raw)) return { text: '', hasTool: false, finished: false }
	const chat = isRecord(raw.chat) ? raw.chat : null
	const message = chat && isRecord(chat.message) ? chat.message : null
	return {
		text: sdkPartsToText(message?.content),
		hasTool: raw.tool != null,
		finished: raw.done === true || chat?.done === true,
	}
}

/** one popover's question-and-answer, from an ephemeral run. */
export class SelectionAssist {
	phase = $state<SelectionAssistPhase>('idle')
	answer = $state('')
	errorMessage = $state('')

	#controller: AbortController | null = null
	#lastPrompt = ''

	get isWorking(): boolean {
		return this.phase === 'loading' || this.phase === 'thinking' || this.phase === 'streaming'
	}

	get canRetry(): boolean {
		return this.phase === 'error' && this.#lastPrompt.length > 0
	}

	/** abort whatever is in flight; the popover's text is left as it is. */
	stop = (): void => {
		this.#controller?.abort()
		this.#controller = null
	}

	reset = (): void => {
		this.stop()
		this.phase = 'idle'
		this.answer = ''
		this.errorMessage = ''
		this.#lastPrompt = ''
	}

	retry = async (): Promise<void> => {
		if (!this.#lastPrompt) return
		await this.run(this.#lastPrompt)
	}

	run = async (prompt: string): Promise<void> => {
		const agentId = selectedAgent.id
		this.#lastPrompt = prompt
		if (!agentId) {
			this.phase = 'error'
			this.errorMessage = 'no agent is selected'
			return
		}

		this.stop()
		const controller = new AbortController()
		this.#controller = controller
		this.phase = 'loading'
		this.answer = ''
		this.errorMessage = ''
		let finished = false

		try {
			const stream = runChatStream({
				agentId,
				threadId: null,
				input: { type: 'user', content: [{ type: 'text', text: prompt }] },
				persist: false,
				signal: controller.signal,
			})
			for await (const event of stream) {
				if (event.event === 'delta') {
					const parsed = parseDelta(event.data.delta)
					if (parsed.hasTool && this.phase === 'loading') this.phase = 'thinking'
					if (parsed.text) {
						this.phase = 'streaming'
						this.answer += parsed.text
					}
					if (parsed.finished) finished = true
				} else if (event.event === 'error') {
					// a run that already delivered its whole answer and then tears
					// itself down is finished, not failed - the reader saw the
					// answer. anything else is a real failure and says so.
					if (finished && this.answer.trim()) break
					throw new Error(event.data.message)
				}
			}
			if (!this.answer.trim()) throw new Error('no answer came back')
			this.phase = 'done'
		} catch (err) {
			if (controller.signal.aborted) return
			this.errorMessage =
				err instanceof Error && err.message ? err.message : 'could not generate an answer'
			this.phase = 'error'
		} finally {
			if (this.#controller === controller) this.#controller = null
		}
	}
}
