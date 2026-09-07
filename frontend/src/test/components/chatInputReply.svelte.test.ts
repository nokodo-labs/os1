/**
 * the composer's reply preview (F134): arming it, retargeting it in place, and
 * every path that dismisses it - the X, escape, and a send. the quote rises out
 * of the composer and sinks back into it, unless motion is off.
 */

import ChatInput from '$lib/components/chat/ChatInput.svelte'
import { device } from '$lib/stores/device.svelte'
import { fireEvent, render, waitFor } from '@testing-library/svelte'
import { tick } from 'svelte'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage } from '../chat/fixtures'

const ada = makeApiMessage({ id: 'msg_ada', content: [{ type: 'text', text: 'the first one' }] })
const bob = makeApiMessage({ id: 'msg_bob', content: [{ type: 'text', text: 'the other one' }] })

function preview(container: HTMLElement): HTMLElement | null {
	return container.querySelector('[data-reply-preview]')
}

function mount(props: Record<string, unknown> = {}) {
	return render(ChatInput, {
		props: { replyTo: ada, replyToAuthor: 'ada', onCancelReply: () => {}, ...props },
	})
}

/** arms after mount, the way a bubble's reply action does: the entrance plays. */
async function mountThenArm(props: Record<string, unknown> = {}) {
	const harness = mount({ replyTo: null, ...props })
	await harness.rerender({ replyTo: ada, replyToAuthor: 'ada' })
	await tick()
	return harness
}

interface AnimateSpy {
	mock: { calls: unknown[][] }
}

/** durations svelte handed to the web animations api for this render. */
function transitionDurations(spy: AnimateSpy): number[] {
	return spy.mock.calls.map((call) => {
		const options = call[1]
		return typeof options === 'object' && options !== null && 'duration' in options
			? Number(options.duration)
			: -1
	})
}

/**
 * the shared animations stub never settles, and svelte drives every step of a
 * transition off `onfinish` - without one that fires, an outro'd preview would
 * never leave the dom here. scoped to this file so the shared one stays as is.
 */
function settlingAnimate() {
	let cancelled = false
	const animation = {
		currentTime: 0,
		playState: 'finished',
		effect: null,
		onfinish: null as (() => void) | null,
		finished: Promise.resolve(),
		cancel: () => {
			cancelled = true
		},
	}
	queueMicrotask(() => {
		if (!cancelled) animation.onfinish?.()
	})
	return animation
}

const sharedAnimate = Element.prototype.animate

function useAnimate(value: unknown): void {
	Object.defineProperty(Element.prototype, 'animate', {
		configurable: true,
		writable: true,
		value,
	})
}

beforeEach(() => {
	device.prefersReducedMotion = false
	useAnimate(settlingAnimate)
})

afterEach(() => {
	vi.restoreAllMocks()
	useAnimate(sharedAnimate)
	device.prefersReducedMotion = false
})

describe('reply preview', () => {
	it('is armed by a reply target, quote and dismiss button included', async () => {
		const { container } = await mountThenArm()

		const armed = preview(container)
		expect(armed).not.toBeNull()
		expect(armed?.textContent).toContain('ada')
		expect(armed?.textContent).toContain('the first one')
		expect(container.querySelector('[aria-label="cancel reply"]')).not.toBeNull()
	})

	it('renders nothing while no reply is armed', () => {
		const { container } = mount({ replyTo: null })

		expect(preview(container)).toBeNull()
	})

	it('stays out of the composer in search mode', () => {
		const { container } = mount({ mode: 'search' })

		expect(preview(container)).toBeNull()
	})

	it('rises on a 260ms timeline when motion is allowed', async () => {
		const animate = vi.spyOn(Element.prototype, 'animate')
		await mountThenArm()

		expect(transitionDurations(animate)).toContain(260)
	})

	it('arrives and leaves instantly under reduced motion', async () => {
		device.prefersReducedMotion = true
		const animate = vi.spyOn(Element.prototype, 'animate')
		const { container, rerender } = await mountThenArm()

		// a zero-duration transition never reaches the animations api at all
		expect(preview(container)).not.toBeNull()
		expect(transitionDurations(animate)).toHaveLength(0)

		await rerender({ replyTo: null })
		await tick()

		expect(preview(container)).toBeNull()
		expect(transitionDurations(animate)).toHaveLength(0)
	})

	it('the X asks the owner to drop the reply, and the preview leaves', async () => {
		const onCancelReply = vi.fn()
		const { container, rerender } = mount({ onCancelReply })

		const dismiss = container.querySelector('[aria-label="cancel reply"]')
		expect(dismiss).not.toBeNull()
		await fireEvent.click(dismiss as HTMLElement)
		expect(onCancelReply).toHaveBeenCalledTimes(1)

		await rerender({ replyTo: null })
		await waitFor(() => expect(preview(container)).toBeNull())
	})

	it('escape drops the reply', async () => {
		const onCancelReply = vi.fn()
		const { container, rerender } = mount({ onCancelReply })

		await fireEvent.keyDown(window, { key: 'Escape' })
		expect(onCancelReply).toHaveBeenCalledTimes(1)

		await rerender({ replyTo: null })
		await waitFor(() => expect(preview(container)).toBeNull())
	})

	it('escape yields to an armed agent before it touches the reply', async () => {
		const onCancelReply = vi.fn()
		mount({ onCancelReply, armedAgentId: 'agent_1' })

		await fireEvent.keyDown(window, { key: 'Escape' })

		expect(onCancelReply).not.toHaveBeenCalled()
	})

	it('sending carries the reply and then drops it', async () => {
		const onCancelReply = vi.fn()
		const onSubmit = vi.fn()
		const { container, rerender } = mount({ onCancelReply, onSubmit, value: 'hi' })

		const form = container.querySelector('form')
		expect(form).not.toBeNull()
		await fireEvent.submit(form as HTMLFormElement)

		expect(onSubmit).toHaveBeenCalledWith(
			'hi',
			expect.objectContaining({ replyToMessageId: 'msg_ada' })
		)
		expect(onCancelReply).toHaveBeenCalledTimes(1)

		await rerender({ replyTo: null })
		await waitFor(() => expect(preview(container)).toBeNull())
	})

	it('retargets in place instead of replaying the entrance', async () => {
		const animate = vi.spyOn(Element.prototype, 'animate')
		const { container, rerender } = await mountThenArm()
		const armed = preview(container)
		animate.mockClear()

		await rerender({ replyTo: bob, replyToAuthor: 'bob' })
		await tick()

		// same node, and no second rise: the composer is already open, so only
		// the quote swaps - on the shorter 140ms fade
		expect(preview(container)).toBe(armed)
		expect(armed?.textContent).toContain('the other one')
		expect(armed?.textContent).not.toContain('the first one')
		const durations = transitionDurations(animate)
		expect(durations).not.toContain(260)
		expect(durations).toContain(140)
	})
})
