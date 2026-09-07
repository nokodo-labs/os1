import { longpress } from '$lib/attachments/longpress'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

const haptics = vi.hoisted(() => ({ hapticFeedback: vi.fn() }))
vi.mock('$lib/utils/haptics', () => haptics)

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

function click(type: 'click' | 'contextmenu' = 'click'): MouseEvent {
	return new MouseEvent(type, { bubbles: true, cancelable: true })
}

describe('longpress', () => {
	let node: HTMLButtonElement
	let onLongPress: Mock<(event: PointerEvent) => void>
	let onClick: Mock<(event: MouseEvent) => void>
	let detach: (() => void) | void

	beforeEach(() => {
		vi.useFakeTimers()
		haptics.hapticFeedback.mockReset()
		node = document.createElement('button')
		document.body.appendChild(node)
		onLongPress = vi.fn<(event: PointerEvent) => void>()
		onClick = vi.fn<(event: MouseEvent) => void>()
		node.addEventListener('click', onClick)
		detach = longpress({ onLongPress })(node)
	})

	afterEach(() => {
		detach?.()
		node.remove()
		vi.useRealTimers()
	})

	it('fires after the hold and swallows the release click', () => {
		node.dispatchEvent(pointer('pointerdown'))
		vi.advanceTimersByTime(449)
		expect(onLongPress).not.toHaveBeenCalled()
		vi.advanceTimersByTime(1)
		expect(onLongPress).toHaveBeenCalledTimes(1)
		expect(haptics.hapticFeedback).toHaveBeenCalledTimes(1)

		node.dispatchEvent(pointer('pointerup'))
		node.dispatchEvent(click())
		expect(onClick).not.toHaveBeenCalled()
	})

	it('a short mouse tap is the native click, once', () => {
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'mouse' }))
		vi.advanceTimersByTime(200)
		node.dispatchEvent(pointer('pointerup', { pointerType: 'mouse' }))
		vi.advanceTimersByTime(500)
		node.dispatchEvent(click())
		expect(onLongPress).not.toHaveBeenCalled()
		expect(onClick).toHaveBeenCalledTimes(1)
	})

	it('a touch hold fires and releases without a click', () => {
		node.dispatchEvent(pointer('pointerdown', { pointerType: 'touch' }))
		vi.advanceTimersByTime(450)
		node.dispatchEvent(pointer('pointerup', { pointerType: 'touch' }))
		expect(onLongPress).toHaveBeenCalledTimes(1)
		expect(onClick).not.toHaveBeenCalled()
	})

	it('cancels when the pointer wanders', () => {
		node.dispatchEvent(pointer('pointerdown'))
		node.dispatchEvent(pointer('pointermove', { clientX: 40 }))
		vi.advanceTimersByTime(500)
		expect(onLongPress).not.toHaveBeenCalled()
	})

	it('ignores secondary buttons', () => {
		node.dispatchEvent(pointer('pointerdown', { button: 2 }))
		vi.advanceTimersByTime(500)
		expect(onLongPress).not.toHaveBeenCalled()
	})

	it('keeps the click when shouldStart turns a press down', () => {
		detach?.()
		detach = longpress({ onLongPress, shouldStart: () => false })(node)
		node.dispatchEvent(pointer('pointerdown'))
		vi.advanceTimersByTime(500)
		node.dispatchEvent(pointer('pointerup'))
		node.dispatchEvent(click())

		expect(onLongPress).not.toHaveBeenCalled()
		expect(onClick).toHaveBeenCalledTimes(1)
	})

	it('attaches nothing while disabled', () => {
		detach?.()
		detach = longpress({ onLongPress, disabled: true })(node)
		node.dispatchEvent(pointer('pointerdown'))
		vi.advanceTimersByTime(500)
		expect(onLongPress).not.toHaveBeenCalled()
	})

	it('suppresses the native context menu while pressing', () => {
		node.dispatchEvent(pointer('pointerdown'))
		const menu = click('contextmenu')
		node.dispatchEvent(menu)
		expect(menu.defaultPrevented).toBe(true)

		node.dispatchEvent(pointer('pointerup'))
		const idle = click('contextmenu')
		node.dispatchEvent(idle)
		expect(idle.defaultPrevented).toBe(false)
	})
})
