import { swallowclick } from '$lib/attachments/swallowclick'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

function click(): MouseEvent {
	return new MouseEvent('click', { bubbles: true, cancelable: true })
}

describe('swallowclick', () => {
	let node: HTMLDivElement
	let button: HTMLButtonElement
	let onButton: Mock<() => void>
	let onSwallow: Mock<() => void>
	let armed: boolean
	let detach: (() => void) | void

	beforeEach(() => {
		node = document.createElement('div')
		button = document.createElement('button')
		node.appendChild(button)
		document.body.appendChild(node)
		onButton = vi.fn<() => void>()
		onSwallow = vi.fn<() => void>()
		button.addEventListener('click', onButton)
		armed = false
		detach = swallowclick({ when: () => armed, onSwallow })(node)
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
	})

	it('lets a click through while it is not armed', () => {
		button.dispatchEvent(click())

		expect(onButton).toHaveBeenCalledTimes(1)
		expect(onSwallow).not.toHaveBeenCalled()
	})

	it('eats an armed click before the target sees it', () => {
		armed = true
		const event = click()
		button.dispatchEvent(event)

		expect(onButton).not.toHaveBeenCalled()
		expect(event.defaultPrevented).toBe(true)
		expect(onSwallow).toHaveBeenCalledTimes(1)
	})

	it('eats one click per arming', () => {
		armed = true
		onSwallow.mockImplementation(() => {
			armed = false
		})

		button.dispatchEvent(click())
		button.dispatchEvent(click())

		expect(onButton).toHaveBeenCalledTimes(1)
		expect(onSwallow).toHaveBeenCalledTimes(1)
	})

	it('stops guarding once detached', () => {
		armed = true
		detach?.()
		detach = undefined

		button.dispatchEvent(click())

		expect(onButton).toHaveBeenCalledTimes(1)
		expect(onSwallow).not.toHaveBeenCalled()
	})
})
