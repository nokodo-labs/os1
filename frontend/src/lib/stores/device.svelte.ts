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

/**
 * synchronous pre-init values from media queries.
 * these run at module load (before any $effect or onMount) so the first
 * render already uses the correct layout, preventing flashes on mobile.
 */
const preInitMobile = browser ? window.innerWidth < DEVICE_MOBILE_BREAKPOINT_PX : false
const preInitTouch = browser ? window.matchMedia('(pointer: coarse)').matches : false
const preInitCoarsePointer = preInitTouch
const preInitHasHover = browser ? window.matchMedia('(hover: hover)').matches : true

export const device = $state({
	ready: false,
	width: 0,
	height: 0,
	viewportWidth: 0,
	viewportHeight: 0,
	dpr: 1,
	breakpointPx: DEVICE_MOBILE_BREAKPOINT_PX,
	isMobile: preInitMobile,
	isTouch: preInitTouch,
	isCoarsePointer: preInitCoarsePointer,
	hasHover: preInitHasHover,
	gpuTier: 'mid' as GpuTier,
	gpuDiagnostics: { ...GPU_DIAGNOSTICS_DEFAULT },

	// client context fields (populated once at init)
	timezone: '',
	language: '',
	os: '',
	browserName: '',
	isChromium: false,
	pwaInstalled: false,

	// geolocation (populated when useLocation is enabled)
	latitude: null as number | null,
	longitude: null as number | null,
	locationLabel: null as string | null,

	// virtual keyboard state (mobile only)
	virtualKeyboardOpen: false,
	virtualKeyboardHeight: 0,
})

type Cleanup = () => void

let didInit = false
let cleanup: Cleanup | null = null
let rafId: number | null = null
let dprMql: MediaQueryList | null = null
let dprCleanup: Cleanup | null = null

// virtual keyboard detection state
let keyboardBaselineHeight = 0
let keyboardBaselineWidth = 0

/** input types that trigger the virtual keyboard on mobile */
const KEYBOARD_INPUT_TYPES = new Set([
	'text',
	'email',
	'number',
	'password',
	'search',
	'tel',
	'url',
	'date',
	'datetime-local',
	'month',
	'time',
	'week',
])

/**
 * check whether the currently focused element would trigger a virtual keyboard.
 * uses a whitelist of known keyboard-triggering input types so unknown/new
 * types default to "no keyboard" (safe) instead of false positives.
 */
function isEditableElementFocused(): boolean {
	const el = document.activeElement
	if (!el) return false
	if (el instanceof HTMLTextAreaElement) return true
	if (el instanceof HTMLElement && el.isContentEditable) return true
	if (el instanceof HTMLInputElement) {
		return KEYBOARD_INPUT_TYPES.has(el.type.toLowerCase())
	}
	return false
}

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
	device.isMobile = preInitMobile
	device.isTouch = preInitTouch
	device.isCoarsePointer = preInitCoarsePointer
	device.hasHover = preInitHasHover
	device.gpuTier = 'mid'
	device.gpuDiagnostics = { ...GPU_DIAGNOSTICS_DEFAULT }
	device.timezone = ''
	device.language = ''
	device.os = ''
	device.browserName = ''
	device.isChromium = false
	device.pwaInstalled = false
	device.virtualKeyboardOpen = false
	device.virtualKeyboardHeight = 0
}

/**
 * detect graphical performance tier using available browser signals.
 * combines WebGL renderer info, hardware concurrency, device memory,
 * and mobile/touch heuristics to estimate GPU capability.
 */

function detectTimezone(): string {
	try {
		return Intl.DateTimeFormat().resolvedOptions().timeZone || ''
	} catch {
		return ''
	}
}

function detectLanguage(): string {
	try {
		return navigator.language || ''
	} catch {
		return ''
	}
}

function detectOS(): string {
	try {
		const nav = navigator as Navigator & {
			userAgentData?: { platform?: string }
		}
		if (nav.userAgentData?.platform) return nav.userAgentData.platform

		const ua = navigator.userAgent
		if (ua.includes('Win')) return 'Windows'
		if (ua.includes('Mac')) return 'macOS'
		if (ua.includes('Linux')) return 'Linux'
		if (ua.includes('Android')) return 'Android'
		if (ua.includes('iPhone') || ua.includes('iPad')) return 'iOS'
		if (ua.includes('CrOS')) return 'ChromeOS'
		return ''
	} catch {
		return ''
	}
}

function detectBrowser(): string {
	try {
		const nav = navigator as Navigator & {
			userAgentData?: { brands?: Array<{ brand: string; version: string }> }
		}
		if (nav.userAgentData?.brands) {
			const known = nav.userAgentData.brands.find(
				(b) =>
					!b.brand.includes('Not') &&
					!b.brand.includes('Chromium') &&
					b.brand !== 'Chromium'
			)
			if (known) return known.brand
		}
		const ua = navigator.userAgent
		if (ua.includes('Firefox/')) return 'Firefox'
		if (ua.includes('Edg/')) return 'Edge'
		if (ua.includes('OPR/') || ua.includes('Opera/')) return 'Opera'
		if (ua.includes('Chrome/')) return 'Chrome'
		if (ua.includes('Safari/') && !ua.includes('Chrome')) return 'Safari'
		return ''
	} catch {
		return ''
	}
}

function detectChromium(): boolean {
	try {
		const nav = navigator as Navigator & {
			userAgentData?: { brands?: Array<{ brand: string }> }
		}
		if (nav.userAgentData?.brands) {
			return nav.userAgentData.brands.some((b) => b.brand === 'Chromium')
		}
		return /Chrome\//.test(navigator.userAgent) && !/Firefox/.test(navigator.userAgent)
	} catch {
		return false
	}
}

function detectPwaInstalled(): boolean {
	try {
		return window.matchMedia('(display-mode: standalone)').matches
	} catch {
		return false
	}
}

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

	// virtual keyboard detection
	const vvHeight = window.visualViewport?.height ?? window.innerHeight

	// reset baseline on orientation change (width shift > 100px)
	if (Math.abs(window.innerWidth - keyboardBaselineWidth) > 100) {
		keyboardBaselineHeight = vvHeight
		keyboardBaselineWidth = window.innerWidth
	}

	// baseline ratchets up when viewport grows (keyboard closing, address bar hiding)
	if (vvHeight > keyboardBaselineHeight) {
		keyboardBaselineHeight = vvHeight
	}

	const kbDiff = keyboardBaselineHeight - vvHeight
	const kbOpen = device.isMobile && kbDiff > 150 && isEditableElementFocused()

	device.virtualKeyboardOpen = kbOpen
	device.virtualKeyboardHeight = kbOpen ? Math.round(kbDiff) : 0

	// drive layout height via CSS custom property:
	// when keyboard is open, shrink to the actual visible area;
	// otherwise, remove the override and let the CSS default (100dvh) apply.
	if (kbOpen) {
		document.documentElement.style.setProperty('--app-height', `${Math.round(vvHeight)}px`)
	} else {
		document.documentElement.style.removeProperty('--app-height')
	}

	// prevent overscrolling past the visible area when keyboard is open.
	// the class locks html/body overflow via CSS.
	document.documentElement.classList.toggle('virtual-keyboard-open', kbOpen)
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

	// set keyboard baseline before first sync
	keyboardBaselineHeight = window.visualViewport?.height ?? window.innerHeight
	keyboardBaselineWidth = window.innerWidth

	// initial sync before any components read values
	syncNow()

	// detect GPU tier once at startup (depends on isMobile/isTouch from syncNow)
	const detected = detectGpuTier()
	device.gpuTier = detected.tier
	device.gpuDiagnostics = detected.diagnostics

	// detect client context fields once at startup
	device.timezone = detectTimezone()
	device.language = detectLanguage()
	device.os = detectOS()
	device.browserName = detectBrowser()
	device.isChromium = detectChromium()
	device.pwaInstalled = detectPwaInstalled()

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
	keyboardBaselineHeight = 0
	keyboardBaselineWidth = 0
	document.documentElement.style.removeProperty('--app-height')
	document.documentElement.classList.remove('virtual-keyboard-open')
	resetDeviceState()
}

/** build the client context payload for agent run requests. */
export function getClientContext(): {
	timezone: string
	language: string
	os: string
	browser: string
	pwaInstalled: boolean
	screenWidth: number
	screenHeight: number
	isMobile: boolean
	latitude: number | null
	longitude: number | null
	locationLabel: string | null
} {
	return {
		timezone: device.timezone,
		language: device.language,
		os: device.os,
		browser: device.browserName,
		pwaInstalled: device.pwaInstalled,
		screenWidth: device.width,
		screenHeight: device.height,
		isMobile: device.isMobile,
		latitude: device.latitude,
		longitude: device.longitude,
		locationLabel: device.locationLabel,
	}
}

/**
 * request geolocation from the browser and cache it in device state.
 * call this when the user enables the useLocation privacy preference.
 * silently does nothing if geolocation is unavailable or denied.
 */
export function requestGeolocation(): void {
	if (!browser) return
	if (!navigator.geolocation) return

	navigator.geolocation.getCurrentPosition(
		(position) => {
			device.latitude = position.coords.latitude
			device.longitude = position.coords.longitude
		},
		() => {
			// permission denied or error — leave as null
			device.latitude = null
			device.longitude = null
			device.locationLabel = null
		},
		{ enableHighAccuracy: false, timeout: 5000, maximumAge: 300_000 }
	)
}

/** clear cached geolocation data. */
export function clearGeolocation(): void {
	device.latitude = null
	device.longitude = null
	device.locationLabel = null
}
