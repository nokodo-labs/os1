import { contextmenu } from '$lib/attachments/contextmenu'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

const haptics = vi.hoisted(() => ({ hapticFeedback: vi.fn() }))
vi.mock('$lib/utils/haptics', () => haptics)

const ROW_RECT = {
	x: 100,
	y: 20,
	top: 20,
	left: 100,
	right: 300,
	bottom: 60,
	width: 200,
	height: 40,
	toJSON: () => ({}),
}

function pointer(type: string, init: PointerEventInit = {}): PointerEvent {
	return new PointerEvent(type, {
		bubbles: true,
		cancelable: true,
		pointerId: 1,
		isPrimary: true,
		button: 0,
		clientX: 10,
		clientY: 10,
		...init,
	})
}

function mouse(type: 'click' | 'contextmenu', init: MouseEventInit = {}): MouseEvent {
	return new MouseEvent(type, { bubbles: true, cancelable: true, ...init })
}

describe('contextmenu', () => {
	let node: HTMLDivElement
	let field: HTMLInputElement
	let action: HTMLButtonElement
	let onOpen: Mock<(anchor: { x: number; y: number; source: string }) => void>
	let onClick: Mock<(event: MouseEvent) => void>
	let detach: (() => void) | void

	beforeEach(() => {
		vi.useFakeTimers()
		haptics.hapticFeedback.mockReset()
		node = document.createElement('div')
		node.getBoundingClientRect = () => ROW_RECT
		field = document.createElement('input')
		action = document.createElement('button')
		node.append(field, action)
		document.body.appendChild(node)
		onOpen = vi.fn<(anchor: { x: number; y: number; source: string }) => void>()
		onClick = vi.fn<(event: MouseEvent) => void>()
		node.addEventListener('click', onClick)
		detach = contextmenu({ onOpen })(node)
	})

	afterEach(() => {
		detach?.()
		node.remove()
		vi.useRealTimers()
	})

	it('opens at the pointer on right-click and swallows the native menu', () => {
		node.dispatchEvent(pointer('pointerdown', { button: 2 }))
		const menu = mouse('contextmenu', { clientX: 240, clientY: 130 })
		node.dispatchEvent(menu)

		expect(menu.defaultPrevented).toBe(true)
		expect(onOpen).toHaveBeenCalledTimes(1)
		expect(onOpen).toHaveBeenCalledWith({ x: 240, y: 130, source: 'pointer' })
	})

	it('opens at the row on a touch hold, once', () => {
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(450)

		expect(onOpen).toHaveBeenCalledTimes(1)
		expect(onOpen).toHaveBeenCalledWith({
			x: ROW_RECT.left,
			y: ROW_RECT.bottom,
			source: 'hold',
		})

		// the native menu android raises on the same hold is not a second open
		const menu = mouse('contextmenu')
		node.dispatchEvent(menu)
		expect(menu.defaultPrevented).toBe(true)
		expect(onOpen).toHaveBeenCalledTimes(1)
	})

	it('anchors a hold to the near edge of the screen', () => {
		const right = window.innerWidth - 100
		node.getBoundingClientRect = () => ({ ...ROW_RECT, left: right - 200, right })
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(450)

		expect(onOpen).toHaveBeenCalledWith({ x: right, y: ROW_RECT.bottom, source: 'hold' })
	})

	it('leaves a mouse hold alone, click and all', () => {
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'mouse' }))
		vi.advanceTimersByTime(600)
		node.dispatchEvent(pointer('pointerup', { pointerType: 'mouse' }))
		node.dispatchEvent(mouse('click'))

		expect(onOpen).not.toHaveBeenCalled()
		expect(onClick).toHaveBeenCalledTimes(1)
	})

	it('leaves text entry inside the row to the browser', () => {
		const menu = mouse('contextmenu')
		field.dispatchEvent(menu)
		expect(menu.defaultPrevented).toBe(false)
		expect(onOpen).not.toHaveBeenCalled()

		field.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(600)
		expect(onOpen).not.toHaveBeenCalled()
	})

	it('still opens over a button in the row, which the row menu covers', () => {
		action.dispatchEvent(mouse('contextmenu', { clientX: 12, clientY: 34 }))
		expect(onOpen).toHaveBeenCalledWith({ x: 12, y: 34, source: 'pointer' })
	})

	it('attaches nothing while disabled', () => {
		detach?.()
		detach = contextmenu({ onOpen, disabled: true })(node)
		node.dispatchEvent(mouse('contextmenu'))
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(600)

		expect(onOpen).not.toHaveBeenCalled()
	})

	it('stops listening once detached', () => {
		detach?.()
		detach = undefined
		node.dispatchEvent(mouse('contextmenu'))
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(600)

		expect(onOpen).not.toHaveBeenCalled()
	})
})
