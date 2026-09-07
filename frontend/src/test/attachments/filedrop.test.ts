import { filedrop } from '$lib/attachments/filedrop'
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

interface FakeTransfer {
	types: string[]
	files: { length: number }
	dropEffect: string
}

function transfer(options: { files?: number; types?: string[] }): FakeTransfer {
	return {
		types: options.types ?? ['Files'],
		files: { length: options.files ?? 0 },
		dropEffect: 'none',
	}
}

function dragEvent(type: string, dataTransfer: FakeTransfer | null): Event {
	const event = new Event(type, { bubbles: true, cancelable: true })
	Object.defineProperty(event, 'dataTransfer', { value: dataTransfer })
	return event
}

describe('filedrop', () => {
	let node: HTMLDivElement
	let child: HTMLSpanElement
	let onDrop: Mock<(files: FileList) => void>
	let onActiveChange: Mock<(active: boolean) => void>
	let detach: (() => void) | void

	beforeEach(() => {
		node = document.createElement('div')
		child = document.createElement('span')
		node.appendChild(child)
		document.body.appendChild(node)
		onDrop = vi.fn()
		onActiveChange = vi.fn()
		detach = filedrop({ onDrop, onActiveChange })(node)
	})

	afterEach(() => {
		detach?.()
		detach = undefined
		node.remove()
	})

	it('hands dropped files over and claims the drop', () => {
		const data = transfer({ files: 2 })
		node.dispatchEvent(dragEvent('dragenter', data))
		node.dispatchEvent(dragEvent('dragover', data))
		const drop = dragEvent('drop', data)
		node.dispatchEvent(drop)

		expect(onDrop).toHaveBeenCalledTimes(1)
		expect(onDrop.mock.calls[0][0]).toBe(data.files)
		expect(drop.defaultPrevented).toBe(true)
	})

	it('accepts the drag so the browser does not open the file itself', () => {
		const data = transfer({ files: 1 })
		const over = dragEvent('dragover', data)
		node.dispatchEvent(over)

		expect(over.defaultPrevented).toBe(true)
		expect(data.dropEffect).toBe('copy')
	})

	it('ignores a drag that carries no files', () => {
		const data = transfer({ types: ['text/plain'] })
		const over = dragEvent('dragover', data)
		node.dispatchEvent(over)
		node.dispatchEvent(dragEvent('drop', data))

		expect(over.defaultPrevented).toBe(false)
		expect(onDrop).not.toHaveBeenCalled()
		expect(onActiveChange).not.toHaveBeenCalled()
	})

	it('stays active while the drag moves between children', () => {
		const data = transfer({ files: 1 })
		node.dispatchEvent(dragEvent('dragenter', data))
		child.dispatchEvent(dragEvent('dragenter', data))
		node.dispatchEvent(dragEvent('dragleave', data))

		expect(onActiveChange.mock.calls).toEqual([[true]])

		child.dispatchEvent(dragEvent('dragleave', data))

		expect(onActiveChange.mock.calls).toEqual([[true], [false]])
	})

	it('clears the active state once the files are dropped', () => {
		const data = transfer({ files: 1 })
		node.dispatchEvent(dragEvent('dragenter', data))
		node.dispatchEvent(dragEvent('drop', data))

		expect(onActiveChange.mock.calls).toEqual([[true], [false]])
	})

	it('does nothing while disabled', () => {
		detach?.()
		detach = filedrop({ onDrop, onActiveChange, disabled: true })(node)
		const data = transfer({ files: 1 })
		node.dispatchEvent(dragEvent('dragenter', data))
		node.dispatchEvent(dragEvent('drop', data))

		expect(onDrop).not.toHaveBeenCalled()
		expect(onActiveChange).not.toHaveBeenCalled()
	})

	it('stops listening once detached', () => {
		detach?.()
		detach = undefined
		const data = transfer({ files: 1 })
		const drop = dragEvent('drop', data)
		node.dispatchEvent(drop)

		expect(onDrop).not.toHaveBeenCalled()
		expect(drop.defaultPrevented).toBe(false)
	})
})
