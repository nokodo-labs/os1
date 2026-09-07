/**
 * the think tool's row in the transcript (F144): a verb that rotates while the
 * thought runs, an elapsed counter that rolls one digit at a time, and an icon
 * that breathes until the thought lands.
 */

import { THINKING_VERBS } from '$lib/chat/thinkingVerbs'
import ThinkingVerb from '$lib/components/chat/tools/ThinkingVerb.svelte'
import ToolStep from '$lib/components/chat/tools/ToolStep.svelte'
import DigitRoll from '$lib/components/common/DigitRoll.svelte'
import { device } from '$lib/stores/device.svelte'
import type { ToolExecution } from '$lib/tools'
import { render } from '@testing-library/svelte'
import { flushSync } from 'svelte'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => {
	vi.useFakeTimers()
})

afterEach(() => {
	vi.useRealTimers()
	vi.restoreAllMocks()
	device.prefersReducedMotion = false
})

/** pins the rotation to one end of its 3-5s window (1 = the long hold). */
function pinRotation(roll: number) {
	vi.spyOn(Math, 'random').mockReturnValue(roll)
}

/** the verb currently on screen. */
function verb(container: HTMLElement): string {
	const el = container.querySelector('[data-thinking-verb]')
	if (!(el instanceof HTMLElement)) throw new Error('no rotating verb on the row')
	return el.dataset.thinkingVerb ?? ''
}

function think(status: ToolExecution['status'], extra: Partial<ToolExecution> = {}): ToolExecution {
	return {
		toolCall: { id: 'call_think', name: 'think', arguments: {} },
		status,
		events: [],
		startedAt: new Date(),
		...extra,
	}
}

describe('the rotating thinking verb', () => {
	it('opens on a verb from the library and shimmers it', () => {
		const { container } = render(ThinkingVerb)
		flushSync()

		expect(THINKING_VERBS).toContain(verb(container))
		expect(container.querySelector('.shimmer')?.textContent).toBe(verb(container))
	})

	it('swaps to a new verb every few seconds, keeping the old one for the roll', () => {
		pinRotation(1)
		const { container } = render(ThinkingVerb)
		flushSync()
		const first = verb(container)

		vi.advanceTimersByTime(5000)
		flushSync()

		const second = verb(container)
		expect(second).not.toBe(first)
		expect(THINKING_VERBS).toContain(second)
		const swap = container.querySelector('[data-swapping]')
		expect(swap).not.toBeNull()
		expect(container.querySelector('.verb-out')?.textContent).toBe(first)
		expect(container.querySelector('.verb-in')?.textContent).toBe(second)

		vi.advanceTimersByTime(240)
		flushSync()

		expect(container.querySelector('.verb-out')).toBeNull()
		expect(container.querySelector('[data-swapping]')).toBeNull()
	})

	it('holds a verb for at least three seconds', () => {
		pinRotation(0)
		const { container } = render(ThinkingVerb)
		flushSync()
		const first = verb(container)

		vi.advanceTimersByTime(2900)
		flushSync()
		expect(verb(container)).toBe(first)

		vi.advanceTimersByTime(100)
		flushSync()
		expect(verb(container)).not.toBe(first)
	})

	it('swaps without the roll when motion is off', () => {
		device.prefersReducedMotion = true
		pinRotation(1)
		const { container } = render(ThinkingVerb)
		flushSync()
		const first = verb(container)

		vi.advanceTimersByTime(5000)
		flushSync()

		expect(verb(container)).not.toBe(first)
		expect(container.querySelector('.verb-out')).toBeNull()
		expect(container.querySelector('[data-swapping]')).toBeNull()
	})

	it('stops rotating once the row is gone', () => {
		const { unmount } = render(ThinkingVerb)
		flushSync()

		unmount()
		flushSync()

		expect(vi.getTimerCount()).toBe(0)
	})
})

describe('the digit-roll counter', () => {
	it('gives every digit its own slot and leaves punctuation alone', () => {
		const { container } = render(DigitRoll, { props: { value: '12.3s' } })
		flushSync()

		expect(container.querySelectorAll('.digit-slot')).toHaveLength(3)
		expect(container.querySelectorAll('.digit-fixed')).toHaveLength(2)
		expect(container.querySelectorAll('[data-rolling]')).toHaveLength(0)
	})

	it('rolls only the digit that changed', async () => {
		const { container, rerender } = render(DigitRoll, { props: { value: '9.9s' } })
		flushSync()

		await rerender({ value: '9.8s' })
		flushSync()

		const rolling = container.querySelectorAll('[data-rolling]')
		expect(rolling).toHaveLength(1)
		expect(rolling[0]?.querySelector('.digit-out')?.textContent).toBe('9')
		expect(rolling[0]?.querySelector('.digit-in')?.textContent).toBe('8')
	})

	it('settles the outgoing digit after the roll', async () => {
		const { container, rerender } = render(DigitRoll, { props: { value: '1.0s' } })
		flushSync()

		await rerender({ value: '2.0s' })
		flushSync()
		expect(container.querySelectorAll('[data-rolling]')).toHaveLength(1)

		vi.advanceTimersByTime(200)
		flushSync()

		expect(container.querySelectorAll('[data-rolling]')).toHaveLength(0)
		expect(container.querySelectorAll('.digit-out')).toHaveLength(0)
		expect(container.textContent).toBe('2.0s')
	})

	it('swaps digits plainly when motion is off', async () => {
		device.prefersReducedMotion = true
		const { container, rerender } = render(DigitRoll, { props: { value: '1.0s' } })
		flushSync()

		await rerender({ value: '2.0s' })
		flushSync()

		expect(container.querySelectorAll('[data-rolling]')).toHaveLength(0)
		expect(container.textContent).toBe('2.0s')
	})
})

describe('the think row', () => {
	it('rotates verbs, rolls the counter, and breathes the icon while running', () => {
		const { container } = render(ToolStep, { props: { execution: think('running') } })
		flushSync()

		expect(THINKING_VERBS).toContain(verb(container))
		expect(container.querySelector('.think-breathing')).not.toBeNull()
		expect(container.querySelector('[data-digit-roll]')?.textContent).toBe('0.0s')

		vi.advanceTimersByTime(1000)
		flushSync()

		expect(container.querySelector('[data-digit-roll]')?.getAttribute('data-digit-roll')).toBe(
			'1.0s'
		)
		expect(container.querySelectorAll('[data-rolling]').length).toBeGreaterThan(0)
	})

	it('settles to the finished label with a still icon', () => {
		const execution = think('completed', {
			completedAt: new Date(),
			result: {
				toolCallId: 'call_think',
				output: JSON.stringify({ elapsed_seconds: 1.2 }),
				isError: false,
			},
		})
		const { container } = render(ToolStep, { props: { execution } })
		flushSync()

		expect(container.textContent).toContain('thought for 1.2s')
		expect(container.querySelector('[data-thinking-verb]')).toBeNull()
		expect(container.querySelector('.think-breathing')).toBeNull()
		expect(container.querySelector('.shimmer')).toBeNull()
	})

	it('keeps a streamed thought title instead of rotating verbs', () => {
		const execution = think('running', {
			toolCall: {
				id: 'call_think',
				name: 'think',
				arguments: { title: 'weighing the tradeoff' },
			},
		})
		const { container } = render(ToolStep, { props: { execution } })
		flushSync()

		expect(container.textContent).toContain('weighing the tradeoff')
		expect(container.querySelector('[data-thinking-verb]')).toBeNull()
	})
})
