import { swipe, type SwipeDirection } from '$lib/attachments/swipe'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

const START_X = 100
const START_Y = 100

/** default threshold of the attachment, mirrored so the tests read intently. */
const THRESHOLD = 64

/** longest a fly-off can take before the attachment hands over anyway. */
const FLY_TIMEOUT = 400

function pointer(type: string, init: PointerEventInit = {}): PointerEvent {
	return new PointerEvent(type, {
		bubbles: true,
		cancelable: true,
		pointerId: 1,
		isPrimary: true,
		pointerType: 'touch',
		button: 0,
		clientX: START_X,
		clientY: START_Y,
		...init,
	})
}

/** travel from the start point, in css px. */
function move(node: HTMLElement, dx: number, dy: number): void {
	node.dispatchEvent(pointer('pointermove', { clientX: START_X + dx, clientY: START_Y + dy }))
}

const TRAVEL: Record<SwipeDirection, [number, number]> = {
	left: [-1, 0],
	right: [1, 0],
	up: [0, -1],
	down: [0, 1],
}

describe('swipe', () => {
	let node: HTMLDivElement
	let onTrigger: Mock<(direction: SwipeDirection) => void>
	let onGrab: Mock<() => void>
	let onRelease: Mock<() => void>
	let detach: (() => void) | void

	beforeEach(() => {
		vi.useFakeTimers()
		node = document.createElement('div')
		document.body.appendChild(node)
		onTrigger = vi.fn<(direction: SwipeDirection) => void>()
		onGrab = vi.fn<() => void>()
		onRelease = vi.fn<() => void>()
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
		vi.useRealTimers()
	})

	it('claims and triggers in each direction it is given', () => {
		for (const direction of ['left', 'right', 'up', 'down'] as const) {
			onTrigger.mockClear()
			detach?.()
			detach = swipe({ direction, onTrigger })(node)

			const [x, y] = TRAVEL[direction]
			node.dispatchEvent(pointer('pointerdown'))
			move(node, x * 20, y * 20)
			expect(node.style.transform).not.toBe('')
			move(node, x * (THRESHOLD + 10), y * (THRESHOLD + 10))
			node.dispatchEvent(pointer('pointerup'))

			expect(onTrigger).toHaveBeenCalledTimes(1)
			expect(onTrigger).toHaveBeenCalledWith(direction)
			vi.advanceTimersByTime(300)
		}
	})

	it('accepts either direction of a set and reports progress for it', () => {
		const onProgress = vi.fn<(progress: number, direction: SwipeDirection) => void>()
		detach = swipe({ direction: ['left', 'right'], onTrigger, onProgress })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, -(THRESHOLD + 20), 0)
		expect(onProgress).toHaveBeenLastCalledWith(1, 'left')
		node.dispatchEvent(pointer('pointerup'))

		expect(onTrigger).toHaveBeenCalledWith('left')
	})

	it('yields to the scroller when the finger drifts across the axis', () => {
		detach = swipe({ direction: 'right', onTrigger, onGrab })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, 30, 20)
		expect(node.style.transform).toBe('')
		// the gesture is gone: further travel does nothing
		move(node, 120, 20)
		node.dispatchEvent(pointer('pointerup'))

		expect(onGrab).not.toHaveBeenCalled()
		expect(onTrigger).not.toHaveBeenCalled()
	})

	it('snaps back without triggering below the threshold', () => {
		detach = swipe({ direction: 'right', onTrigger, onGrab, onRelease })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, 30, 0)
		expect(onGrab).toHaveBeenCalledTimes(1)
		expect(node.style.transform).toBe('translateX(30px)')

		node.dispatchEvent(pointer('pointerup'))
		expect(onTrigger).not.toHaveBeenCalled()
		expect(onRelease).toHaveBeenCalledTimes(1)
		expect(node.style.transform).toBe('')

		vi.advanceTimersByTime(300)
		expect(node.style.transition).toBe('')
	})

	it('ignores travel in a direction it was not given', () => {
		detach = swipe({ direction: 'right', onTrigger, onGrab })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, -(THRESHOLD + 20), 0)
		node.dispatchEvent(pointer('pointerup'))

		expect(node.style.transform).toBe('')
		expect(onGrab).not.toHaveBeenCalled()
		expect(onTrigger).not.toHaveBeenCalled()
	})

	it('flies off before handing over, so the caller can unmount', () => {
		detach = swipe({ direction: 'right', release: 'fly', onTrigger })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, THRESHOLD + 20, 0)
		node.dispatchEvent(pointer('pointerup'))

		expect(onTrigger).not.toHaveBeenCalled()
		expect(node.style.opacity).toBe('0')
		expect(node.style.transform).toContain('translateX(')

		vi.advanceTimersByTime(FLY_TIMEOUT)
		expect(onTrigger).toHaveBeenCalledTimes(1)
		expect(onTrigger).toHaveBeenCalledWith('right')
	})

	it('hands the node back untouched on cleanup', () => {
		detach = swipe({ direction: 'right', release: 'fly', onTrigger })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, THRESHOLD + 20, 0)
		node.dispatchEvent(pointer('pointerup'))
		vi.advanceTimersByTime(FLY_TIMEOUT)

		detach?.()
		detach = undefined
		expect(node.style.transform).toBe('')
		expect(node.style.opacity).toBe('')
		expect(node.style.transition).toBe('')
	})

	it('grabs once and does not release when the gesture triggers', () => {
		detach = swipe({ direction: 'up', onTrigger, onGrab, onRelease })(node)

		node.dispatchEvent(pointer('pointerdown'))
		expect(onGrab).not.toHaveBeenCalled()
		move(node, 0, -5)
		expect(onGrab).not.toHaveBeenCalled()
		move(node, 0, -20)
		move(node, 0, -(THRESHOLD + 20))
		expect(onGrab).toHaveBeenCalledTimes(1)

		node.dispatchEvent(pointer('pointerup'))
		expect(onTrigger).toHaveBeenCalledTimes(1)
		expect(onRelease).not.toHaveBeenCalled()
	})

	it('releases a claimed gesture that is cancelled', () => {
		detach = swipe({ direction: 'right', onTrigger, onGrab, onRelease })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, THRESHOLD + 20, 0)
		node.dispatchEvent(pointer('pointercancel'))

		expect(onRelease).toHaveBeenCalledTimes(1)
		expect(onTrigger).not.toHaveBeenCalled()
	})

	it('ignores the mouse', () => {
		detach = swipe({ direction: 'right', onTrigger })(node)

		node.dispatchEvent(pointer('pointerdown', { pointerType: 'mouse' }))
		node.dispatchEvent(
			pointer('pointermove', { pointerType: 'mouse', clientX: START_X + THRESHOLD + 20 })
		)
		node.dispatchEvent(pointer('pointerup', { pointerType: 'mouse' }))

		expect(node.style.transform).toBe('')
		expect(onTrigger).not.toHaveBeenCalled()
	})

	it('does nothing while disabled', () => {
		detach = swipe({ direction: 'right', enabled: false, onTrigger })(node)

		node.dispatchEvent(pointer('pointerdown'))
		move(node, THRESHOLD + 20, 0)
		node.dispatchEvent(pointer('pointerup'))

		expect(onTrigger).not.toHaveBeenCalled()
	})

	it('owns touch-action per axis and restores it on cleanup', () => {
		node.style.touchAction = 'manipulation'

		detach = swipe({ direction: 'right', onTrigger })(node)
		expect(node.style.touchAction).toBe('pan-y')
		detach?.()
		expect(node.style.touchAction).toBe('manipulation')

		detach = swipe({ direction: ['up', 'down'], onTrigger })(node)
		expect(node.style.touchAction).toBe('pan-x')
		detach?.()

		detach = swipe({ direction: ['up', 'right'], onTrigger })(node)
		expect(node.style.touchAction).toBe('none')
	})

	it('caps travel at maxTravel', () => {
		detach = swipe({ direction: 'up', threshold: 40, maxTravel: 56, onTrigger })(node)
		node.dispatchEvent(pointer('pointerdown'))
		move(node, 0, -300)
		expect(node.style.transform).toMatch(/-56px/)
		node.dispatchEvent(pointer('pointerup'))
		expect(onTrigger).toHaveBeenCalledWith('up')
	})

	it('drags without a css transition and swallows the release click', () => {
		const onClick = vi.fn()
		node.addEventListener('click', onClick)
		detach = swipe({ direction: 'right', onTrigger })(node)
		node.dispatchEvent(pointer('pointerdown'))
		move(node, 20, 0)
		expect(node.style.transition).toBe('none')
		move(node, THRESHOLD + 10, 0)
		node.dispatchEvent(pointer('pointerup'))
		node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
		expect(onClick).not.toHaveBeenCalled()
		node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
		expect(onClick).toHaveBeenCalledTimes(1)
	})
})
