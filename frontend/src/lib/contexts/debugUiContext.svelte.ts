import { browser } from '$app/environment'
import { getContext, setContext } from 'svelte'

const DEBUG_UI_KEY = Symbol('debug-ui')

export type AppsGridIconShape = 'default' | 'circle'

export type StreamdownAnimationType = 'fade' | 'blur' | 'slideUp' | 'slideDown'
export type StreamdownAnimationTokenize = 'word' | 'char'

/** how an outgoing user message animates from the chat input into a bubble. */
export type SendAnimationMode = 'morph' | 'flyup' | 'none'

export interface StreamdownAnimationOptions {
	enabled: boolean
	type: StreamdownAnimationType
	tokenize: StreamdownAnimationTokenize
	duration: number
}

export interface DebugUiContext {
	readonly appsGridIconShape: AppsGridIconShape
	setAppsGridIconShape(shape: AppsGridIconShape): void
	toggleAppsGridIconShape(): void

	readonly streamdownAnimation: StreamdownAnimationOptions
	setStreamdownAnimation(next: Partial<StreamdownAnimationOptions>): void

	readonly sendAnimationMode: SendAnimationMode
	setSendAnimationMode(mode: SendAnimationMode): void
}

const STORAGE_KEY = 'debug.appsGridIconShape'

const STREAMDOWN_ANIMATION_ENABLED_KEY = 'debug.streamdown.animation.enabled'
const STREAMDOWN_ANIMATION_TYPE_KEY = 'debug.streamdown.animation.type'
const STREAMDOWN_ANIMATION_TOKENIZE_KEY = 'debug.streamdown.animation.tokenize'
const STREAMDOWN_ANIMATION_DURATION_KEY = 'debug.streamdown.animation.duration'

const SEND_ANIMATION_MODE_KEY = 'debug.chat.sendAnimationMode'

function readStoredShape(): AppsGridIconShape {
	if (!browser) return 'default'
	const value = window.localStorage.getItem(STORAGE_KEY)
	return value === 'circle' ? 'circle' : 'default'
}

function writeStoredShape(shape: AppsGridIconShape) {
	if (!browser) return
	window.localStorage.setItem(STORAGE_KEY, shape)
}

function readStreamdownAnimation(): StreamdownAnimationOptions {
	if (!browser) {
		return { enabled: true, type: 'fade', tokenize: 'word', duration: 450 }
	}

	const enabledRaw = window.localStorage.getItem(STREAMDOWN_ANIMATION_ENABLED_KEY)
	const typeRaw = window.localStorage.getItem(STREAMDOWN_ANIMATION_TYPE_KEY)
	const tokenizeRaw = window.localStorage.getItem(STREAMDOWN_ANIMATION_TOKENIZE_KEY)
	const durationRaw = window.localStorage.getItem(STREAMDOWN_ANIMATION_DURATION_KEY)

	const enabled = enabledRaw === null ? true : enabledRaw === 'true'

	const type: StreamdownAnimationType =
		typeRaw === 'blur' || typeRaw === 'slideUp' || typeRaw === 'slideDown' ? typeRaw : 'fade'

	const tokenize: StreamdownAnimationTokenize = tokenizeRaw === 'char' ? 'char' : 'word'

	const parsedDuration = durationRaw ? Number.parseInt(durationRaw, 10) : NaN
	const duration = Number.isFinite(parsedDuration)
		? Math.min(3000, Math.max(50, parsedDuration))
		: 450

	return { enabled, type, tokenize, duration }
}

function writeStreamdownAnimation(next: StreamdownAnimationOptions) {
	if (!browser) return
	window.localStorage.setItem(STREAMDOWN_ANIMATION_ENABLED_KEY, String(next.enabled))
	window.localStorage.setItem(STREAMDOWN_ANIMATION_TYPE_KEY, next.type)
	window.localStorage.setItem(STREAMDOWN_ANIMATION_TOKENIZE_KEY, next.tokenize)
	window.localStorage.setItem(STREAMDOWN_ANIMATION_DURATION_KEY, String(next.duration))
}

function readSendAnimationMode(): SendAnimationMode {
	if (!browser) return 'morph'
	const value = window.localStorage.getItem(SEND_ANIMATION_MODE_KEY)
	return value === 'flyup' || value === 'none' ? value : 'morph'
}

function writeSendAnimationMode(mode: SendAnimationMode) {
	if (!browser) return
	window.localStorage.setItem(SEND_ANIMATION_MODE_KEY, mode)
}

export function createDebugUiContext(): DebugUiContext {
	let appsGridIconShape = $state<AppsGridIconShape>(readStoredShape())
	let streamdownAnimation = $state<StreamdownAnimationOptions>(readStreamdownAnimation())
	let sendAnimationMode = $state<SendAnimationMode>(readSendAnimationMode())

	const context: DebugUiContext = {
		get appsGridIconShape() {
			return appsGridIconShape
		},
		setAppsGridIconShape(shape) {
			appsGridIconShape = shape
			writeStoredShape(shape)
		},
		toggleAppsGridIconShape() {
			const next = appsGridIconShape === 'circle' ? 'default' : 'circle'
			appsGridIconShape = next
			writeStoredShape(next)
		},
		get streamdownAnimation() {
			return streamdownAnimation
		},
		setStreamdownAnimation(next) {
			streamdownAnimation = {
				...streamdownAnimation,
				...next,
			}
			writeStreamdownAnimation(streamdownAnimation)
		},
		get sendAnimationMode() {
			return sendAnimationMode
		},
		setSendAnimationMode(mode) {
			sendAnimationMode = mode
			writeSendAnimationMode(mode)
		},
	}

	setContext(DEBUG_UI_KEY, context)
	return context
}

export function useDebugUi(): DebugUiContext {
	const context = getContext<DebugUiContext>(DEBUG_UI_KEY)
	if (!context) {
		throw new Error('useDebugUi must be used within a DebugUiProvider')
	}
	return context
}

export function tryUseDebugUi(): DebugUiContext | null {
	return getContext<DebugUiContext>(DEBUG_UI_KEY) ?? null
}
