export const DEVICE_MOBILE_BREAKPOINT_PX = 888

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
})

type Cleanup = () => void

let didInit = false
let cleanup: Cleanup | null = null

let rafId: number | null = null
let dprMql: MediaQueryList | null = null

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
	device.isTouch = maxTouchPoints > 0 || device.isCoarsePointer
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
	dprMql = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`)
	const off = addMqListener(dprMql, () => {
		onChange()
		// The query depends on devicePixelRatio, so we must re-register each change.
		setupDprListener(onChange)
	})
	return () => {
		off()
		dprMql = null
	}
}

export function initDevice(): void {
	if (didInit) return
	if (typeof window === 'undefined') return

	didInit = true

	const mqMobile = window.matchMedia(`(max-width: ${DEVICE_MOBILE_BREAKPOINT_PX}px)`)
	const mqCoarsePointer = window.matchMedia('(pointer: coarse)')
	const mqHover = window.matchMedia('(hover: hover)')

	const syncNow = () => syncFromWindow(mqMobile, mqCoarsePointer, mqHover)
	const onEvent = () => scheduleSync(syncNow)

	// initial sync before any components read values
	syncNow()

	const offMobile = addMqListener(mqMobile, onEvent)
	const offCoarsePointer = addMqListener(mqCoarsePointer, onEvent)
	const offHover = addMqListener(mqHover, onEvent)
	const offDpr = setupDprListener(onEvent)

	window.addEventListener('resize', onEvent, { passive: true })
	window.addEventListener('orientationchange', onEvent, { passive: true })
	window.visualViewport?.addEventListener('resize', onEvent, { passive: true })
	window.visualViewport?.addEventListener('scroll', onEvent, { passive: true })

	cleanup = () => {
		offMobile()
		offCoarsePointer()
		offHover()
		offDpr()

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
