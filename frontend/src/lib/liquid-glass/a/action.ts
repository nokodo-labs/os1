import type { Action } from 'svelte/action'
import { spring } from 'svelte/motion'
import type { Readable } from 'svelte/store'
import { glassPresets } from './presets'
import type { GlassInput, GlassPreset, GlassState } from './types'

/** only these properties get spring-animated */
const ANIMATED_KEYS = ['blur', 'refractiveIndex', 'specularOpacity'] as const
type AnimatedKey = (typeof ANIMATED_KEYS)[number]

type NumberSpring = Readable<number> & { set: (v: number) => void }

const ACTION_CLASS = 'liquid-glass-action'

function resolvePreset(input: GlassInput): GlassPreset {
	return typeof input === 'string' ? glassPresets[input] : input
}

function resolveTarget(base: GlassState, override?: Partial<GlassState>): GlassState {
	return override ? { ...base, ...override } : base
}

function applyProps(node: HTMLElement, values: Record<AnimatedKey, number>, base: GlassState) {
	const { blur, refractiveIndex, specularOpacity } = values
	const { glassThickness, bezelWidth } = base

	/* map refractiveIndex to backdrop-filter properties that
	   create a convincing "light bending" feel */
	const saturate = 1 + (refractiveIndex - 1) * 0.3
	const brightness = 1 + (refractiveIndex - 1) * 0.05

	node.style.setProperty('--glass-blur', `${blur}px`)
	node.style.setProperty('--glass-saturate', `${saturate}`)
	node.style.setProperty('--glass-brightness', `${brightness}`)
	node.style.setProperty('--glass-bg-alpha', `${glassThickness / 400}`)
	node.style.setProperty('--glass-specular', `${specularOpacity}`)
	node.style.setProperty('--glass-bezel', `${bezelWidth}px`)
}

/**
 * svelte action that turns any element into a glass surface.
 *
 * accepts a preset name ('subtle' | 'standard' | 'heavy' | 'nav' | 'panel')
 * or a full GlassPreset object. spring-animates blur, saturate, brightness
 * on hover / focus / active state changes.
 *
 * @example
 * ```svelte
 * <button use:liquidGlass={'nav'} class="rounded-full p-3">click me</button>
 * ```
 */
export const liquidGlass: Action<HTMLElement, GlassInput> = (node, input) => {
	let preset = resolvePreset(input)
	const cfg = preset.spring ?? { stiffness: 0.12, damping: 0.7 }

	const springs: Record<AnimatedKey, NumberSpring> = {
		blur: spring(preset.base.blur, cfg),
		refractiveIndex: spring(preset.base.refractiveIndex, cfg),
		specularOpacity: spring(preset.base.specularOpacity, cfg),
	}

	const current: Record<AnimatedKey, number> = {
		blur: preset.base.blur,
		refractiveIndex: preset.base.refractiveIndex,
		specularOpacity: preset.base.specularOpacity,
	}

	const unsubs = ANIMATED_KEYS.map((key) =>
		springs[key].subscribe((v) => {
			current[key] = v
			applyProps(node, current, preset.base)
		})
	)

	node.classList.add(ACTION_CLASS)
	applyProps(node, current, preset.base)

	/* interaction state machine: active > focus > hover > base */
	let hovered = false
	let focused = false
	let active = false

	function sync() {
		let target: GlassState
		if (active && preset.active) {
			target = resolveTarget(preset.base, preset.active)
		} else if (focused && preset.focus) {
			target = resolveTarget(preset.base, preset.focus)
		} else if (hovered && preset.hover) {
			target = resolveTarget(preset.base, preset.hover)
		} else {
			target = preset.base
		}

		for (const key of ANIMATED_KEYS) {
			springs[key].set(target[key])
		}
	}

	/* focusin/focusout bubble, so child focus (e.g. input inside a glass panel)
	   triggers the parent's focus state - matches the expected behavior */
	const on = (e: string, fn: EventListener) => {
		node.addEventListener(e, fn)
		return () => node.removeEventListener(e, fn)
	}

	const offs = [
		on('mouseenter', () => {
			hovered = true
			sync()
		}),
		on('mouseleave', () => {
			hovered = false
			sync()
		}),
		on('focusin', () => {
			focused = true
			sync()
		}),
		on('focusout', () => {
			focused = false
			sync()
		}),
		on('pointerdown', () => {
			active = true
			sync()
		}),
		on('pointerup', () => {
			active = false
			sync()
		}),
	]

	return {
		update(newInput: GlassInput) {
			preset = resolvePreset(newInput)
			sync()
		},
		destroy() {
			unsubs.forEach((u) => u())
			offs.forEach((off) => off())
			node.classList.remove(ACTION_CLASS)
		},
	}
}

export const glass = liquidGlass
