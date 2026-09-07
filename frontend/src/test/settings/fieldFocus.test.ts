import {
	cancelSettingsFieldReveal,
	revealSettingsField,
	settingsFieldAnchor,
} from '$lib/components/settings/fieldFocus'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** happy-dom implements neither scrollIntoView nor element.animate. */
function mountField(id: string): {
	node: HTMLElement
	control: HTMLButtonElement
	detach: (() => void) | void
	scrolls: ScrollIntoViewOptions[]
	flashes: Keyframe[][]
} {
	const node = document.createElement('div')
	const control = document.createElement('button')
	node.appendChild(control)
	const scrolls: ScrollIntoViewOptions[] = []
	const flashes: Keyframe[][] = []
	node.scrollIntoView = ((options: ScrollIntoViewOptions) => {
		scrolls.push(options)
	}) as HTMLElement['scrollIntoView']
	// happy-dom exposes animate as a read-only prototype member
	Object.defineProperty(node, 'animate', {
		configurable: true,
		value: (keyframes: Keyframe[]) => {
			flashes.push(keyframes)
			return { cancel: () => {} } as Animation
		},
	})
	document.body.appendChild(node)
	return { node, control, detach: settingsFieldAnchor(id)(node), scrolls, flashes }
}

beforeEach(() => {
	vi.useFakeTimers()
	// the attachment defers the reveal of a late-mounting field by a frame
	vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
		cb(0)
		return 0
	})
})

afterEach(() => {
	cancelSettingsFieldReveal()
	document.body.innerHTML = ''
	vi.useRealTimers()
	vi.unstubAllGlobals()
})

describe('revealSettingsField', () => {
	it('scrolls to, flashes, and focuses a rendered field', async () => {
		const { control, scrolls, flashes } = mountField('theme')

		await expect(revealSettingsField('theme')).resolves.toBe(true)

		expect(scrolls).toEqual([{ block: 'center', behavior: 'smooth' }])
		expect(flashes).toHaveLength(1)
		expect(document.activeElement).toBe(control)
	})

	it('leaves focus alone when asked not to move it', async () => {
		const { control } = mountField('theme')

		await expect(revealSettingsField('theme', { focus: false })).resolves.toBe(true)

		expect(document.activeElement).not.toBe(control)
	})

	it('exposes the field id as a data attribute', () => {
		const { node } = mountField('theme')

		expect(node.dataset.settingsField).toBe('theme')
	})

	it('waits for a field whose section renders later', async () => {
		const promise = revealSettingsField('chat-recall', { wait: 1000 })
		const { scrolls } = mountField('chat-recall')

		await expect(promise).resolves.toBe(true)
		expect(scrolls).toHaveLength(1)
	})

	it('gives up once the wait elapses', async () => {
		const promise = revealSettingsField('never-rendered', { wait: 1000 })
		vi.advanceTimersByTime(1000)

		await expect(promise).resolves.toBe(false)
	})

	it('does not reveal a field whose anchor was destroyed', async () => {
		const { detach } = mountField('theme')
		detach?.()

		await expect(revealSettingsField('theme')).resolves.toBe(false)
	})

	it('cancels a pending reveal on request', async () => {
		const promise = revealSettingsField('theme', { wait: 1000 })
		cancelSettingsFieldReveal()

		await expect(promise).resolves.toBe(false)
	})
})
