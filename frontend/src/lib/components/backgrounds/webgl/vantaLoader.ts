import { wallpaperFrameCap } from '$lib/components/backgrounds/wallpaperLoop'
import { onVisibilityChange } from '$lib/utils/frameLoop'
import * as THREE from 'three'

// vanta owns its own frame loop, so the fields it drives it with are part of the
// surface we rely on: `req` is the pending frame, `prevNow` its previous clock read.
export type VantaEffect = {
	destroy?: () => void
	animationLoop?: () => void
	req?: number
	prevNow?: number
}

type VantaFactory = (options: Record<string, unknown>) => VantaEffect

type VantaNamespace = {
	FOG?: VantaFactory
	CLOUDS?: VantaFactory
	CLOUDS2?: VantaFactory
}

declare global {
	interface Window {
		VANTA?: VantaNamespace
		THREE?: typeof THREE
	}
}

const scriptPromises = new Map<string, Promise<void>>()

function loadScriptOnce(src: string): Promise<void> {
	const existing = scriptPromises.get(src)
	if (existing) return existing

	const promise = new Promise<void>((resolve, reject) => {
		const already = document.querySelector(`script[src="${src}"]`)
		if (already) {
			resolve()
			return
		}

		const script = document.createElement('script')
		script.src = src
		script.async = true
		script.onload = () => resolve()
		script.onerror = () => reject(new Error(`failed to load script: ${src}`))
		document.head.appendChild(script)
	})

	scriptPromises.set(src, promise)
	return promise
}

const cappedEffects = new WeakSet<VantaEffect>()

/**
 * pace a vanta effect at the wallpaper frame cap. vanta re-arms its loop by
 * reading `animationLoop` off the effect every frame, so wrapping that property
 * is enough: an early frame re-arms without rendering, the same re-entry point
 * the visibility pause uses. vanta derives its clock from `prevNow`, so the
 * skipped time still reaches the effect on the frame that does render.
 */
function capVantaFrameRate(effect: VantaEffect): void {
	const original = effect.animationLoop
	if (!original || cappedEffects.has(effect)) return
	cappedEffects.add(effect)

	const minFrameMs = 1000 / wallpaperFrameCap()
	let lastRenderMs: number | null = null

	const throttled = (): void => {
		const now = performance.now()
		if (lastRenderMs !== null && now - lastRenderMs < minFrameMs) {
			effect.req = requestAnimationFrame(throttled)
			return
		}
		lastRenderMs = now
		original.call(effect)
	}

	effect.animationLoop = throttled
}

/**
 * run a vanta effect's internal loop only while the document is visible, so it
 * pauses like the shared frame loop does. clearing `prevNow` drops the hidden
 * gap, which keeps the effect's clock from leaping on resume.
 */
export function syncVantaFrameLoop(effect: VantaEffect): void {
	const visible = typeof document === 'undefined' || document.visibilityState === 'visible'

	// vanta's constructor already started the loop, so cap it before anything else
	capVantaFrameRate(effect)

	if (visible) {
		if (effect.req !== undefined) return
		effect.prevNow = undefined
		effect.animationLoop?.()
	} else if (effect.req !== undefined) {
		cancelAnimationFrame(effect.req)
		effect.req = undefined
	}
}

/** keep a vanta effect's loop in step with document visibility until disposed. */
export function pauseVantaWhileHidden(getEffect: () => VantaEffect | null): () => void {
	return onVisibilityChange(() => {
		const effect = getEffect()
		if (effect) syncVantaFrameLoop(effect)
	})
}

export async function ensureVanta(effectScriptPath: string): Promise<VantaNamespace> {
	window.THREE = THREE
	await loadScriptOnce(effectScriptPath)
	if (!window.VANTA) {
		throw new Error('vanta failed to initialize')
	}
	return window.VANTA
}
