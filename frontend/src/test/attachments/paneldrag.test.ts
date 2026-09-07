import { panelDrag } from '$lib/attachments/paneldrag'
import { PANEL_GESTURE_DEFAULTS } from '$lib/utils/panelGesture'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

const START_X = 100
const START_Y = 400

/** listeners on the scroll path must never be able to block scrolling. */
const SCROLL_PATH_EVENTS = ['touchstart', 'touchmove', 'touchend', 'touchcancel']

function touchList(touches: Touch[]): TouchList {
	const list: Record<number, Touch> = {}
	touches.forEach((touch, index) => (list[index] = touch))
	return Object.assign(list, {
		length: touches.length,
		item: (index: number) => touches[index] ?? null,
		[Symbol.iterator]: () => touches[Symbol.iterator](),
	}) as unknown as TouchList
}

function touchEvent(type: string, x: number, y: number, target: HTMLElement): Event {
	const touch = { identifier: 1, clientX: x, clientY: y, target } as unknown as Touch
	const event = new Event(type, { bubbles: true, cancelable: true })
	Object.defineProperty(event, 'touches', {
		value: touchList(type === 'touchend' ? [] : [touch]),
	})
	Object.defineProperty(event, 'changedTouches', { value: touchList([touch]) })
	Object.defineProperty(event, 'target', { value: target })
	return event
}

function offsetOf(node: HTMLElement): number {
	const match = /translate3d\(0(?:px)?, (-?[\d.]+)px, 0(?:px)?\)/.exec(node.style.transform)
	return match ? Number(match[1]) : 0
}

describe('panelDrag', () => {
	let panel: HTMLDivElement
	let scroller: HTMLDivElement
	let handle: HTMLDivElement
	let onDismiss: Mock<() => void>
	let detach: (() => void) | void
	let time: number

	/** happy-dom reports 0 for both, so the scroller is given a real geometry. */
	function makeScrollable(height: number, content: number): void {
		Object.defineProperty(scroller, 'clientHeight', { value: height, configurable: true })
		Object.defineProperty(scroller, 'scrollHeight', { value: content, configurable: true })
	}

	function fire(type: string, y: number, target: HTMLElement = scroller, x = START_X): void {
		time += 16
		const event = touchEvent(type, x, y, target)
		Object.defineProperty(event, 'timeStamp', { value: time })
		target.dispatchEvent(event)
	}

	beforeEach(() => {
		vi.useFakeTimers()
		time = 0
		panel = document.createElement('div')
		scroller = document.createElement('div')
		scroller.style.overflowY = 'auto'
		handle = document.createElement('div')
		handle.setAttribute('data-panel-handle', '')
		panel.append(handle, scroller)
		document.body.appendChild(panel)
		makeScrollable(200, 800)
		onDismiss = vi.fn<() => void>()
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		panel.remove()
		vi.useRealTimers()
	})

	it('registers every scroll-path listener as passive', () => {
		const node = document.createElement('div')
		const seen = new Map<string, AddEventListenerOptions | boolean | undefined>()
		node.addEventListener = vi.fn((type: string, _listener, options) => {
			seen.set(type, options as AddEventListenerOptions | boolean | undefined)
		}) as unknown as typeof node.addEventListener

		panelDrag({ onDismiss })(node)

		for (const type of SCROLL_PATH_EVENTS) {
			const options = seen.get(type)
			expect(options, `${type} was registered`).toBeTruthy()
			expect(options, `${type} is passive`).toMatchObject({ passive: true })
		}
	})

	it('leaves the panel alone while the content still has somewhere to scroll', () => {
		scroller.scrollTop = 120
		detach = panelDrag({ onDismiss })(panel)

		fire('touchstart', START_Y)
		fire('touchmove', START_Y + 60)
		fire('touchmove', START_Y + 140)

		expect(panel.style.transform).toBe('')
		expect(scroller.style.overflowY).toBe('auto')
	})

	it('hands the same gesture over once the scroller reaches its top', () => {
		scroller.scrollTop = 90
		detach = panelDrag({ onDismiss })(panel)

		fire('touchstart', START_Y)
		fire('touchmove', START_Y + 90)
		// the scroller ran out here; the finger keeps going without lifting
		scroller.scrollTop = 0
		fire('touchmove', START_Y + 100)
		fire('touchmove', START_Y + 150)

		// the drag counts from where the content ran out, not from touchdown
		expect(offsetOf(panel)).toBe(150 - 90 - PANEL_GESTURE_DEFAULTS.claimDistance)
		// no transition may smooth a transform that is following a finger
		expect(panel.style.transition).toBe('none')
		// and the scroller's own scrolling is parked so its bounce cannot fight it
		expect(scroller.style.overflowY).toBe('hidden')
	})

	it('contains overscroll on the scroller it is handed', () => {
		detach = panelDrag({ onDismiss })(panel)
		fire('touchstart', START_Y)
		expect(scroller.style.overscrollBehaviorY).toBe('contain')
	})

	/** a finger, one frame at a time, from touchdown to `distance`. */
	function dragDown(distance: number, perFrame: number): void {
		fire('touchstart', START_Y)
		for (let travelled = perFrame; travelled <= distance; travelled += perFrame) {
			fire('touchmove', START_Y + travelled)
		}
		fire('touchend', START_Y + distance)
	}

	it('never paints the panel above its anchor, drag down then flick hard up', () => {
		detach = panelDrag({ onDismiss })(panel)
		fire('touchstart', START_Y)
		const painted: number[] = []
		for (const y of [40, 90, 140, 60, -120, -400]) {
			fire('touchmove', START_Y + y)
			painted.push(offsetOf(panel))
		}
		expect(Math.min(...painted)).toBe(0)
		expect(offsetOf(panel)).toBe(0)

		fire('touchend', START_Y - 400)
		expect(onDismiss).not.toHaveBeenCalled()
		// a decelerating settle, so the spring cannot carry it past rest either
		expect(panel.style.transition).toContain('cubic-bezier(0.22, 1, 0.36, 1)')
		expect(panel.style.transform).toBe('')
	})

	it('settles back and restores the scroller when the release falls short', () => {
		detach = panelDrag({ onDismiss })(panel)
		dragDown(32, 4)

		expect(onDismiss).not.toHaveBeenCalled()
		expect(offsetOf(panel)).toBe(0)
		expect(scroller.style.overflowY).toBe('auto')
		expect(panel.style.transition).toContain('transform')
	})

	it('flies out and dismisses once, past the threshold', () => {
		detach = panelDrag({ onDismiss })(panel)
		dragDown(160, 8)

		// the panel keeps travelling downward instead of snapping back to rest
		expect(offsetOf(panel)).toBeGreaterThan(160)
		expect(onDismiss).not.toHaveBeenCalled()
		vi.runAllTimers()
		expect(onDismiss).toHaveBeenCalledTimes(1)
	})

	it('dismisses immediately, with no flight, under reduced motion', () => {
		detach = panelDrag({ onDismiss, reducedMotion: () => true })(panel)
		dragDown(160, 8)

		expect(onDismiss).toHaveBeenCalledTimes(1)
		expect(panel.style.transition).toBe('none')
	})

	it('settles with no transition under reduced motion', () => {
		detach = panelDrag({ onDismiss, reducedMotion: () => true })(panel)
		dragDown(32, 4)

		expect(panel.style.transform).toBe('')
		expect(panel.style.transition).toBe('')
	})

	it('ignores a mouse press anywhere but the handle', () => {
		detach = panelDrag({ onDismiss })(panel)
		const down = new PointerEvent('pointerdown', {
			bubbles: true,
			pointerId: 2,
			pointerType: 'mouse',
			clientX: START_X,
			clientY: START_Y,
		})
		scroller.dispatchEvent(down)
		panel.dispatchEvent(
			new PointerEvent('pointermove', {
				pointerId: 2,
				clientX: START_X,
				clientY: START_Y + 120,
			})
		)
		expect(panel.style.transform).toBe('')
	})

	it('lets a mouse drag the panel by its handle', () => {
		panel.setPointerCapture = vi.fn()
		detach = panelDrag({ onDismiss })(panel)
		handle.dispatchEvent(
			new PointerEvent('pointerdown', {
				bubbles: true,
				pointerId: 2,
				pointerType: 'mouse',
				clientX: START_X,
				clientY: START_Y,
			})
		)
		panel.dispatchEvent(
			new PointerEvent('pointermove', {
				pointerId: 2,
				clientX: START_X,
				clientY: START_Y + 120,
			})
		)
		expect(offsetOf(panel)).toBe(120 - PANEL_GESTURE_DEFAULTS.claimDistance)
	})

	it('does not listen for wheel at all - a wheel never grabs a panel', () => {
		const node = document.createElement('div')
		const types: string[] = []
		node.addEventListener = vi.fn((type: string) => {
			types.push(type)
		}) as unknown as typeof node.addEventListener

		panelDrag({ onDismiss })(node)
		expect(types).not.toContain('wheel')
	})
})
