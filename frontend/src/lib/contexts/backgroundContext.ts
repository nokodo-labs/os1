import { getContext, setContext } from 'svelte'

export interface BackgroundContext {
	getCanvas: () => HTMLCanvasElement | null
	getCanvasDimensions: () => { width: number; height: number }
	subscribe: (callback: () => void) => () => void
}

const BACKGROUND_CONTEXT_KEY = Symbol('background')

export function setBackgroundContext(context: BackgroundContext) {
	setContext(BACKGROUND_CONTEXT_KEY, context)
}

export function getBackgroundContext(): BackgroundContext | undefined {
	return getContext(BACKGROUND_CONTEXT_KEY)
}
