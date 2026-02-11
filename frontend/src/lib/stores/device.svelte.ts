import { browser } from '$app/environment'

export const DEVICE_MOBILE_BREAKPOINT_PX = 888

/**
 * graphical performance tier.
 * - high: discrete GPU or powerful integrated — can run WebGL shaders like darkveil
 * - mid: capable but not powerful — lighter shaders like lightrays
 * - low: integrated/software GPU, low-end mobile — prefer static color
 */
export type GpuTier = 'high' | 'mid' | 'low'

export type GpuDiagnostics = {
	score: number
	tier: GpuTier
	cores: number
	memoryGb: number | null
	isMobile: boolean
	isTouch: boolean
	isCoarsePointer: boolean
	hasHover: boolean
	renderer: string | null
	rendererSource: 'debug' | 'default' | 'none'
	webgl: 'webgl2' | 'webgl1' | 'none'
	notes: string[]
}

const GPU_DIAGNOSTICS_DEFAULT: GpuDiagnostics = {
	score: 0,
	tier: 'mid',
	cores: 0,
	memoryGb: null,
	isMobile: false,
	isTouch: false,
	isCoarsePointer: false,
	hasHover: true,
	renderer: null,
	rendererSource: 'none',
	webgl: 'none',
	notes: [],
}

export const device = $state({
	ready: false,
	width: 0,
	height: 0,
	viewportWidth: 0,
	viewportHeight: 0,
	dpr: 1,
	breakpointPx: DEVICE_MOBILE_BREAKPOINT_PX,
	isMobile: false,
	isTouch: false,
	isCoarsePointer: false,
	hasHover: true,
	gpuTier: 'mid' as GpuTier,
	gpuDiagnostics: { ...GPU_DIAGNOSTICS_DEFAULT },
})

type Cleanup = () => void

let didInit = false
let cleanup: Cleanup | null = null
let rafId: number | null = null
let dprMql: MediaQueryList | null = null
let dprCleanup: Cleanup | null = null

function addMqListener(mq: MediaQueryList, handler: () => void) {
	if ('addEventListener' in mq) {
		mq.addEventListener('change', handler)
		return () => mq.removeEventListener('change', handler)
	}
	// older safari
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	;(mq as any).addListener(handler)
	return () => {
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		;(mq as any).removeListener(handler)
	}
}

function resetDeviceState() {
	device.ready = false
	device.width = 0
	device.height = 0
	device.viewportWidth = 0
	device.viewportHeight = 0
	device.dpr = 1
	device.isMobile = false
	device.isTouch = false
	device.isCoarsePointer = false
	device.hasHover = true
	device.gpuTier = 'mid'
	device.gpuDiagnostics = { ...GPU_DIAGNOSTICS_DEFAULT }
}

/**
 * detect graphical performance tier using available browser signals.
 * combines WebGL renderer info, hardware concurrency, device memory,
 * and mobile/touch heuristics to estimate GPU capability.
 */

function readDeviceMemory(): number | null {
	if (!('deviceMemory' in navigator)) return null
	const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory
	if (typeof memory !== 'number') return null
	return memory
}

type RendererInfo = {
	renderer: string | null
	rendererSource: 'debug' | 'default' | 'none'
	webgl: 'webgl2' | 'webgl1' | 'none'
}

function readRendererInfo(): RendererInfo {
	try {
		const canvas = document.createElement('canvas')
		const gl =
			canvas.getContext('webgl2') ??
			canvas.getContext('webgl') ??
			canvas.getContext('experimental-webgl')

		let webgl: RendererInfo['webgl'] = 'none'
		const hasWebgl2 =
			typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext
		const hasWebgl1 =
			typeof WebGLRenderingContext !== 'undefined' && gl instanceof WebGLRenderingContext

		if (hasWebgl2) webgl = 'webgl2'
		else if (hasWebgl1) webgl = 'webgl1'

		let renderer: string | null = null
		let rendererSource: RendererInfo['rendererSource'] = 'none'

		if (gl && (hasWebgl1 || hasWebgl2)) {
			const dbg = gl.getExtension('WEBGL_debug_renderer_info')
			if (dbg) {
				const value = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)
				if (typeof value === 'string') {
					renderer = value
					rendererSource = 'debug'
				}
			}
			if (!renderer) {
				const fallback = gl.getParameter(gl.RENDERER)
				if (typeof fallback === 'string') {
					renderer = fallback
					rendererSource = 'default'
				}
			}

			// explicitly release WebGL context (limited resource in some browsers)
			const loseCtx = gl.getExtension('WEBGL_lose_context')
			loseCtx?.loseContext()
		}

		canvas.width = 0
		canvas.height = 0

		return { renderer, rendererSource, webgl }
	} catch {
		return { renderer: null, rendererSource: 'none', webgl: 'none' }
	}
}

function detectGpuTier(): { tier: GpuTier; diagnostics: GpuDiagnostics } {
	let score = 0
	const notes: string[] = []

	// hardware concurrency (logical cores)
	const cores = navigator.hardwareConcurrency ?? 0
	if (cores >= 12) {
		score += 3
		notes.push('cores >= 12 (+3)')
	} else if (cores >= 8) {
		score += 2
		notes.push('cores >= 8 (+2)')
	} else if (cores >= 4) {
		score += 1
		notes.push('cores >= 4 (+1)')
	} else if (cores > 0) {
		score -= 1
		notes.push('cores < 4 (-1)')
	}

	// device memory (gb) — chrome/edge only
	const memory = readDeviceMemory()
	if (memory !== null) {
		if (memory >= 16) {
			score += 3
			notes.push('memory >= 16gb (+3)')
		} else if (memory >= 8) {
			score += 2
			notes.push('memory >= 8gb (+2)')
		} else if (memory >= 4) {
			score += 1
			notes.push('memory >= 4gb (+1)')
		} else if (memory < 2) {
			score -= 1
			notes.push('memory < 2gb (-1)')
		}
	} else {
		notes.push('device memory unavailable')
	}

	// mobile/touch penalty
	if (device.isMobile || device.isTouch) {
		score -= 1
		notes.push('mobile or touch (-1)')
	}

	// WebGL renderer string heuristics
	const rendererInfo = readRendererInfo()
	if (!rendererInfo.renderer) {
		notes.push('renderer unavailable')
	} else {
		const lower = rendererInfo.renderer.toLowerCase()

		if (
			lower.includes('swiftshader') ||
			lower.includes('llvmpipe') ||
			lower.includes('software')
		) {
			score -= 4
			notes.push('software renderer (-4)')
		} else if (lower.includes('rtx') || lower.includes('geforce') || lower.includes('nvidia')) {
			score += 3
			notes.push('nvidia gpu (+3)')
		} else if (lower.includes('radeon') || /\brx\s?\d/.test(lower) || lower.includes('rdna')) {
			score += 2
			notes.push('amd gpu (+2)')
		} else if (lower.includes('apple')) {
			score += 2
			notes.push('apple gpu (+2)')
		} else if (lower.includes('intel')) {
			if (lower.includes('iris') || lower.includes('arc')) {
				score += 1
				notes.push('intel iris/arc (+1)')
			} else {
				score -= 1
				notes.push('older intel (-1)')
			}
		} else if (lower.includes('adreno')) {
			score += 0
			notes.push('qualcomm adreno (+0)')
		} else if (lower.includes('mali')) {
			score -= 1
			notes.push('arm mali (-1)')
		}
	}

	let tier: GpuTier = 'mid'
	if (score >= 5) tier = 'high'
	else if (score <= -1) tier = 'low'

	return {
		tier,
		diagnostics: {
			score,
			tier,
			cores,
			memoryGb: memory,
			isMobile: device.isMobile,
			isTouch: device.isTouch,
			isCoarsePointer: device.isCoarsePointer,
			hasHover: device.hasHover,
			renderer: rendererInfo.renderer,
			rendererSource: rendererInfo.rendererSource,
			webgl: rendererInfo.webgl,
			notes,
		},
	}
}

function syncFromWindow(
	mqMobile: MediaQueryList | null,
	mqCoarsePointer: MediaQueryList | null,
	mqHover: MediaQueryList | null
) {
	device.width = window.innerWidth
	device.height = window.innerHeight
	device.viewportWidth = window.visualViewport?.width ?? window.innerWidth
	device.viewportHeight = window.visualViewport?.height ?? window.innerHeight
	device.dpr = window.devicePixelRatio || 1
	device.isMobile = mqMobile?.matches ?? window.innerWidth <= device.breakpointPx
	device.isCoarsePointer = mqCoarsePointer?.matches ?? false
	device.hasHover = mqHover?.matches ?? true

	const maxTouchPoints = navigator.maxTouchPoints || 0
	device.isTouch = device.isCoarsePointer || (maxTouchPoints > 0 && !device.hasHover)
	device.ready = true
}

function scheduleSync(syncNow: () => void) {
	if (rafId !== null) return
	rafId = window.requestAnimationFrame(() => {
		rafId = null
		syncNow()
	})
}

function setupDprListener(onChange: () => void) {
	dprCleanup?.()
	dprMql = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`)
	const off = addMqListener(dprMql, () => {
		onChange()
		// the query depends on devicePixelRatio, so we must re-register each change.
		setupDprListener(onChange)
	})
	dprCleanup = () => {
		off()
		dprMql = null
	}
}

export function initDevice(): void {
	if (didInit) return
	if (!browser) return
	didInit = true

	const mqMobile = window.matchMedia(`(max-width: ${DEVICE_MOBILE_BREAKPOINT_PX}px)`)
	const mqCoarsePointer = window.matchMedia('(pointer: coarse)')
	const mqHover = window.matchMedia('(hover: hover)')

	const syncNow = () => syncFromWindow(mqMobile, mqCoarsePointer, mqHover)
	const onEvent = () => scheduleSync(syncNow)

	// initial sync before any components read values
	syncNow()

	// detect GPU tier once at startup (depends on isMobile/isTouch from syncNow)
	const detected = detectGpuTier()
	device.gpuTier = detected.tier
	device.gpuDiagnostics = detected.diagnostics

	const offMobile = addMqListener(mqMobile, onEvent)
	const offCoarsePointer = addMqListener(mqCoarsePointer, onEvent)
	const offHover = addMqListener(mqHover, onEvent)
	setupDprListener(onEvent)

	window.addEventListener('resize', onEvent, { passive: true })
	window.addEventListener('orientationchange', onEvent, { passive: true })
	window.visualViewport?.addEventListener('resize', onEvent, { passive: true })
	window.visualViewport?.addEventListener('scroll', onEvent, { passive: true })

	cleanup = () => {
		offMobile()
		offCoarsePointer()
		offHover()
		dprCleanup?.()
		dprCleanup = null

		if (rafId !== null) {
			window.cancelAnimationFrame(rafId)
			rafId = null
		}

		window.removeEventListener('resize', onEvent)
		window.removeEventListener('orientationchange', onEvent)
		window.visualViewport?.removeEventListener('resize', onEvent)
		window.visualViewport?.removeEventListener('scroll', onEvent)
	}

	if (import.meta.hot) {
		import.meta.hot.dispose(() => {
			destroyDevice()
		})
	}
}

export function destroyDevice(): void {
	cleanup?.()
	cleanup = null
	didInit = false
	resetDeviceState()
}
