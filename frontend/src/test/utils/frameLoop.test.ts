import { onVisibilityChange, startFrameLoop } from '$lib/utils/frameLoop'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

let frameCallbacks: Map<number, FrameRequestCallback>
let nextFrameId: number
let clockMs: number
let visibility: DocumentVisibilityState

/** advance the fake clock and run every frame callback scheduled so far. */
function flushFrame(advanceMs: number): void {
	clockMs += advanceMs
	const due = [...frameCallbacks.values()]
	frameCallbacks.clear()
	for (const callback of due) callback(clockMs)
}

function setVisibility(state: DocumentVisibilityState): void {
	visibility = state
	document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
	frameCallbacks = new Map()
	nextFrameId = 1
	clockMs = 0
	visibility = 'visible'

	Object.defineProperty(document, 'visibilityState', {
		configurable: true,
		get: () => visibility,
	})

	vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback): number => {
		const id = nextFrameId++
		frameCallbacks.set(id, callback)
		return id
	})
	vi.stubGlobal('cancelAnimationFrame', (id: number): void => {
		frameCallbacks.delete(id)
	})
})

afterEach(() => {
	vi.unstubAllGlobals()
})

describe('startFrameLoop', () => {
	it('renders once per frame while the document is visible', () => {
		const render = vi.fn()
		const stop = startFrameLoop(render)

		expect(render).not.toHaveBeenCalled()

		flushFrame(16)
		flushFrame(16)
		flushFrame(16)

		expect(render.mock.calls).toEqual([
			[0, 0],
			[16, 16],
			[32, 16],
		])

		stop()
	})

	it('does not start while the document is already hidden', () => {
		visibility = 'hidden'
		const render = vi.fn()
		const stop = startFrameLoop(render)

		flushFrame(16)
		expect(render).not.toHaveBeenCalled()

		setVisibility('visible')
		flushFrame(16)
		expect(render).toHaveBeenCalledTimes(1)

		stop()
	})

	it('pauses while hidden and resumes without a dt spike', () => {
		const render = vi.fn()
		const stop = startFrameLoop(render)

		flushFrame(16)
		flushFrame(16)
		expect(render).toHaveBeenCalledTimes(2)

		setVisibility('hidden')
		flushFrame(5000)
		flushFrame(5000)
		expect(render).toHaveBeenCalledTimes(2)

		setVisibility('visible')
		flushFrame(16)

		// the clock keeps its pre-pause value and the gap contributes no dt
		expect(render).toHaveBeenCalledTimes(3)
		expect(render).toHaveBeenLastCalledWith(16, 0)

		flushFrame(16)
		expect(render).toHaveBeenLastCalledWith(32, 16)

		stop()
	})

	it('clamps a long frame gap so the clock cannot leap', () => {
		const render = vi.fn()
		const stop = startFrameLoop(render)

		flushFrame(16)
		flushFrame(5000)

		expect(render).toHaveBeenLastCalledWith(100, 100)

		stop()
	})

	it('skips frames to honour maxFps', () => {
		const render = vi.fn()
		const stop = startFrameLoop(render, { maxFps: 50 })

		for (let i = 0; i < 5; i++) flushFrame(10)

		expect(render.mock.calls).toEqual([
			[0, 0],
			[20, 20],
			[40, 20],
		])

		stop()
	})

	it('stops the loop and ignores repeated stop calls', () => {
		const render = vi.fn()
		const stop = startFrameLoop(render)

		flushFrame(16)
		expect(render).toHaveBeenCalledTimes(1)

		stop()
		stop()

		expect(frameCallbacks.size).toBe(0)

		flushFrame(16)
		setVisibility('hidden')
		setVisibility('visible')
		flushFrame(16)

		expect(render).toHaveBeenCalledTimes(1)
	})
})

describe('onVisibilityChange', () => {
	it('reports visibility until it is disposed', () => {
		const onChange = vi.fn()
		const dispose = onVisibilityChange(onChange)

		setVisibility('hidden')
		setVisibility('visible')
		expect(onChange.mock.calls).toEqual([[false], [true]])

		dispose()
		setVisibility('hidden')
		expect(onChange).toHaveBeenCalledTimes(2)
	})
})
