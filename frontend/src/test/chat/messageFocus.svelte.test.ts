import {
	cancelMessageReveal,
	MESSAGE_FLASH_MS,
	messageAnchor,
	revealMessage,
} from '$lib/chat/messageFocus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** happy-dom implements neither scrollIntoView nor element.animate. */
function mountAnchor(id: string | null): {
	node: HTMLElement
	detach: (() => void) | void
	scrolls: ScrollIntoViewOptions[]
	flashes: Keyframe[][]
	timings: KeyframeAnimationOptions[]
} {
	const node = document.createElement('div')
	const scrolls: ScrollIntoViewOptions[] = []
	const flashes: Keyframe[][] = []
	const timings: KeyframeAnimationOptions[] = []
	node.scrollIntoView = ((options: ScrollIntoViewOptions) => {
		scrolls.push(options)
	}) as HTMLElement['scrollIntoView']
	// happy-dom exposes animate as a read-only prototype member
	Object.defineProperty(node, 'animate', {
		configurable: true,
		value: (keyframes: Keyframe[], timing: KeyframeAnimationOptions) => {
			flashes.push(keyframes)
			timings.push(timing)
			return { cancel: () => {} } as Animation
		},
	})
	document.body.appendChild(node)
	return { node, detach: messageAnchor(id)(node), scrolls, flashes, timings }
}

beforeEach(() => {
	vi.useFakeTimers()
	// the attachment defers the reveal of a late-mounting message by a frame
	vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
		cb(0)
		return 0
	})
})

afterEach(() => {
	cancelMessageReveal()
	document.body.innerHTML = ''
	vi.useRealTimers()
	vi.unstubAllGlobals()
})

describe('revealMessage', () => {
	it('scrolls to and flashes a mounted message', async () => {
		const { scrolls, flashes } = mountAnchor('message_1')

		await expect(revealMessage('message_1', { block: 'center' })).resolves.toBe(true)

		expect(scrolls).toEqual([{ block: 'center', behavior: 'auto' }])
		expect(flashes).toHaveLength(1)
	})

	it('holds the reply highlight for seconds, not a blink', async () => {
		const { flashes, timings } = mountAnchor('message_1')

		await expect(revealMessage('message_1')).resolves.toBe(true)

		expect(MESSAGE_FLASH_MS).toBe(3400)
		expect(timings[0]?.duration).toBe(MESSAGE_FLASH_MS)
		// rise, hold, fade: the tint is still full a third of the way through
		const offsets = flashes[0]?.map((frame) => frame.offset)
		expect(offsets).toEqual([0, 0.06, 0.88, 1])
	})

	it('exposes the id as a data attribute for external tooling', () => {
		const { node } = mountAnchor('message_1')

		expect(node.dataset.messageId).toBe('message_1')
	})

	it('resolves false immediately when the message is absent and no wait is asked', async () => {
		await expect(revealMessage('message_missing')).resolves.toBe(false)
	})

	it('waits for a message that mounts later, then reveals it', async () => {
		const promise = revealMessage('message_late', { wait: 1000 })
		const { scrolls, flashes } = mountAnchor('message_late')

		await expect(promise).resolves.toBe(true)
		expect(scrolls).toHaveLength(1)
		expect(flashes).toHaveLength(1)
	})

	it('gives up once the wait elapses', async () => {
		const promise = revealMessage('message_never', { wait: 1000 })
		vi.advanceTimersByTime(1000)

		await expect(promise).resolves.toBe(false)
	})

	it('a newer request supersedes one that is still waiting', async () => {
		const first = revealMessage('message_a', { wait: 1000 })
		const second = revealMessage('message_b', { wait: 1000 })
		mountAnchor('message_b')

		await expect(first).resolves.toBe(false)
		await expect(second).resolves.toBe(true)
	})

	it('does not reveal a message whose anchor was destroyed', async () => {
		const { detach } = mountAnchor('message_1')
		detach?.()

		await expect(revealMessage('message_1')).resolves.toBe(false)
	})

	it('follows an anchor whose id changes', async () => {
		// a changed id re-runs the attachment: cleanup, then a fresh registration
		const { node, detach, scrolls } = mountAnchor('message_old')
		detach?.()
		messageAnchor('message_new')(node)

		await expect(revealMessage('message_old')).resolves.toBe(false)
		await expect(revealMessage('message_new')).resolves.toBe(true)
		expect(scrolls).toHaveLength(1)
	})

	it('registers nothing for a null id', async () => {
		mountAnchor(null)

		await expect(revealMessage('')).resolves.toBe(false)
	})

	it('cancels a pending reveal on request', async () => {
		const promise = revealMessage('message_pending', { wait: 1000 })
		cancelMessageReveal()

		await expect(promise).resolves.toBe(false)
	})
})
