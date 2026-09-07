import { scrollGesture, type ScrollGestureDirection } from '$lib/attachments/scrollgesture'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

describe('scrollGesture', () => {
	let node: HTMLDivElement
	let onGesture: Mock<(direction: ScrollGestureDirection) => void>
	let detach: (() => void) | void

	beforeEach(() => {
		node = document.createElement('div')
		document.body.appendChild(node)
		onGesture = vi.fn<(direction: ScrollGestureDirection) => void>()
		detach = scrollGesture(onGesture)(node)
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
	})

	it('reports which way the wheel went', () => {
		node.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: -40 }))
		expect(onGesture).toHaveBeenLastCalledWith('up')

		node.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: 40 }))
		expect(onGesture).toHaveBeenLastCalledWith('down')
	})

	it('reports touch travel without a direction', () => {
		node.dispatchEvent(new Event('touchmove', { bubbles: true }))

		expect(onGesture).toHaveBeenCalledExactlyOnceWith('unknown')
	})

	it('ignores a programmatic scroll', () => {
		node.dispatchEvent(new Event('scroll', { bubbles: true }))

		expect(onGesture).not.toHaveBeenCalled()
	})

	it('stops listening once detached', () => {
		detach?.()
		detach = undefined

		node.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: 40 }))
		node.dispatchEvent(new Event('touchmove', { bubbles: true }))

		expect(onGesture).not.toHaveBeenCalled()
	})
})
