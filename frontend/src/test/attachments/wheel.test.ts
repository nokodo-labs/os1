import { passiveWheel, wheelToHScroll } from '$lib/attachments/wheel'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

function wheel(init: WheelEventInit = {}): WheelEvent {
	return new WheelEvent('wheel', { bubbles: true, cancelable: true, ...init })
}

describe('passiveWheel', () => {
	let node: HTMLDivElement
	let onWheel: Mock<(event: WheelEvent) => void>
	let detach: (() => void) | void

	beforeEach(() => {
		node = document.createElement('div')
		document.body.appendChild(node)
		onWheel = vi.fn<(event: WheelEvent) => void>()
		detach = passiveWheel(onWheel)(node)
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
	})

	it('hands every wheel event to the caller', () => {
		node.dispatchEvent(wheel({ deltaY: 120 }))

		expect(onWheel).toHaveBeenCalledTimes(1)
		expect(onWheel.mock.calls[0][0].deltaY).toBe(120)
	})

	it('stops listening once detached', () => {
		detach?.()
		detach = undefined

		node.dispatchEvent(wheel({ deltaY: 120 }))

		expect(onWheel).not.toHaveBeenCalled()
	})

	it('re-subscribes to a handler that changed', () => {
		const next = vi.fn<(event: WheelEvent) => void>()
		detach?.()
		detach = passiveWheel(next)(node)

		node.dispatchEvent(wheel({ deltaY: 120 }))

		expect(onWheel).not.toHaveBeenCalled()
		expect(next).toHaveBeenCalledTimes(1)
	})
})

describe('wheelToHScroll', () => {
	let node: HTMLDivElement
	let detach: (() => void) | void

	beforeEach(() => {
		node = document.createElement('div')
		document.body.appendChild(node)
		detach = wheelToHScroll()(node)
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
	})

	it('turns vertical travel into sideways travel', () => {
		const event = wheel({ deltaY: 40 })
		node.dispatchEvent(event)

		expect(node.scrollLeft).toBe(40)
		expect(event.defaultPrevented).toBe(true)
	})

	it('leaves a purely horizontal wheel to the browser', () => {
		const event = wheel({ deltaX: 40 })
		node.dispatchEvent(event)

		expect(node.scrollLeft).toBe(0)
		expect(event.defaultPrevented).toBe(false)
	})

	it('stops redirecting once detached', () => {
		detach?.()
		detach = undefined

		node.dispatchEvent(wheel({ deltaY: 40 }))

		expect(node.scrollLeft).toBe(0)
	})
})
