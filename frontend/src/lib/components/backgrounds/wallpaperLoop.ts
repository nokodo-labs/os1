// frame pacing for wallpapers.
//
// wallpapers stay dumb about the device: they start their loop through here and
// the device's tier cap (`background.wallpaperMaxFps`) is applied for them.

import { background } from '$lib/stores/background.svelte'
import { startFrameLoop, type FrameLoopOptions, type FrameLoopRender } from '$lib/utils/frameLoop'

/**
 * cap used when a wallpaper animates on a tier that has no frame budget.
 * resolution keeps animated wallpapers off such devices, so only debug tooling
 * reaches this - it still has to animate, just cheaply.
 */
const NO_BUDGET_FALLBACK_FPS = 30

/** the device cap, tightened by a wallpaper's own preferred cap when it has one. */
export function wallpaperFrameCap(preferredMaxFps?: number): number {
	const deviceCap = background.wallpaperMaxFps || NO_BUDGET_FALLBACK_FPS
	return preferredMaxFps === undefined ? deviceCap : Math.min(deviceCap, preferredMaxFps)
}

/** start a wallpaper frame loop paced for this device. */
export function startWallpaperLoop(
	render: FrameLoopRender,
	options: FrameLoopOptions = {}
): () => void {
	return startFrameLoop(render, { maxFps: wallpaperFrameCap(options.maxFps) })
}
