import { createAnchorFocus } from '$lib/utils/anchorFocus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** happy-dom implements neither scrollIntoView nor element.animate. */
function mountNode(): {
	node: HTMLElement
	scrolls: ScrollIntoViewOptions[]
	flashes: Keyframe[][]
	timings: KeyframeAnimationOptions[]
} {
	const node = document.createElement('div')
	const scrolls: ScrollIntoViewOptions[] = []
	const flashes: Keyframe[][] = []
	const timings: KeyframeAnimationOptions[] = []
	node.scrollIntoView = (options?: boolean | ScrollIntoViewOptions) => {
		if (options && typeof options !== 'boolean') scrolls.push(options)
	}
	// happy-dom exposes animate as a read-only prototype member
	Object.defineProperty(node, 'animate', {
		configurable: true,
		value: (keyframes: Keyframe[], timing: KeyframeAnimationOptions) => {
			flashes.push(keyframes)
			timings.push(timing)
			return { cancel: () => {} }
		},
	})
	document.body.appendChild(node)
	return { node, scrolls, flashes, timings }
}

beforeEach(() => {
	vi.useFakeTimers()
	vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
		cb(0)
		return 0
	})
})

afterEach(() => {
	document.body.innerHTML = ''
	vi.useRealTimers()
	vi.unstubAllGlobals()
})

describe('createAnchorFocus', () => {
	it('keeps ids and pending reveals per instance', async () => {
		const messages = createAnchorFocus()
		const reminders = createAnchorFocus()
		const { node } = mountNode()
		reminders.anchor('shared_id')(node)

		// same id, other instance: not registered there
		await expect(messages.reveal('shared_id')).resolves.toBe(false)
		await expect(reminders.reveal('shared_id')).resolves.toBe(true)

		// a reveal waiting in one instance survives a reveal in the other
		const waiting = messages.reveal('late_id', { wait: 1000 })
		await expect(reminders.reveal('shared_id')).resolves.toBe(true)
		const late = mountNode()
		messages.anchor('late_id')(late.node)
		await expect(waiting).resolves.toBe(true)
	})

	it('flashes with the corner radius it was built for', async () => {
		const focus = createAnchorFocus({ radius: '2rem' })
		const { node, flashes } = mountNode()
		focus.anchor('reminder_1')(node)

		await expect(focus.reveal('reminder_1')).resolves.toBe(true)

		expect(flashes[0]?.every((frame) => frame.borderRadius === '2rem')).toBe(true)
	})

	it('flashes for the duration it was built for, holding before it fades', async () => {
		const fast = createAnchorFocus()
		const slow = createAnchorFocus({ flashMs: 3000 })
		const a = mountNode()
		const b = mountNode()
		fast.anchor('a')(a.node)
		slow.anchor('b')(b.node)

		await expect(fast.reveal('a')).resolves.toBe(true)
		await expect(slow.reveal('b')).resolves.toBe(true)

		expect(a.timings[0]?.duration).toBe(650)
		expect(b.timings[0]?.duration).toBe(3000)
		// full tint is held across two keyframes, so the fade is a tail, not a blink
		const tinted = b.flashes[0]?.filter((frame) => frame.backgroundColor !== 'transparent')
		expect(tinted).toHaveLength(2)
		expect(tinted?.[0]?.backgroundColor).toBe(tinted?.[1]?.backgroundColor)
	})

	it('marks registered nodes when asked to', () => {
		const focus = createAnchorFocus({
			mark: (node, id) => {
				node.dataset.messageId = id
			},
		})
		const { node } = mountNode()
		focus.anchor('message_1')(node)

		expect(node.dataset.messageId).toBe('message_1')
	})
})
