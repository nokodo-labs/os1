import {
	BACKGROUND_DEFAULTS,
	BACKGROUND_LUMINANCE,
	BACKGROUND_RENDERER,
	BACKGROUND_TYPES,
	BACKGROUND_VARIANT,
	type BackgroundRenderer,
} from '$lib/components/backgrounds/backgroundDefaults'
import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
import { describe, expect, it } from 'vitest'

/** wallpapers grouped by the component that paints them */
function siblingsByRenderer(): Map<BackgroundRenderer, BackgroundType[]> {
	const groups = new Map<BackgroundRenderer, BackgroundType[]>()
	for (const type of BACKGROUND_TYPES) {
		const renderer = BACKGROUND_RENDERER[type]
		groups.set(renderer, [...(groups.get(renderer) ?? []), type])
	}
	return groups
}

describe('wallpaper catalogue', () => {
	it('lists every wallpaper exactly once', () => {
		expect(BACKGROUND_TYPES.length).toBe(Object.keys(BACKGROUND_RENDERER).length)
		expect(new Set(BACKGROUND_TYPES).size).toBe(BACKGROUND_TYPES.length)
	})

	it('gives every wallpaper defaults, a renderer, a variant tag and a luminance', () => {
		for (const type of BACKGROUND_TYPES) {
			expect(BACKGROUND_DEFAULTS[type]).toBeDefined()
			expect(BACKGROUND_RENDERER[type]).toBeDefined()
			expect(BACKGROUND_VARIANT[type]).not.toBeUndefined()
			expect(BACKGROUND_LUMINANCE[type]).toBeDefined()
		}
	})
})

describe('light and dark pairs', () => {
	it('pairs every tagged wallpaper with one sibling of the opposite variant', () => {
		for (const [renderer, siblings] of siblingsByRenderer()) {
			if (siblings.every((type) => BACKGROUND_VARIANT[type] === null)) continue

			const variants = siblings.map((type) => BACKGROUND_VARIANT[type])
			expect(variants, renderer).toHaveLength(2)
			expect(new Set(variants), renderer).toEqual(new Set(['light', 'dark']))
		}
	})

	it('excludes only static and none, which have no pair to tag', () => {
		const untagged = BACKGROUND_TYPES.filter((type) => BACKGROUND_VARIANT[type] === null)
		expect(untagged).toEqual(['static', 'none'])
	})

	it('keeps luminance following the wallpaper, so glass tints match what it paints', () => {
		for (const type of BACKGROUND_TYPES) {
			const variant = BACKGROUND_VARIANT[type]
			if (variant === null) continue
			expect(BACKGROUND_LUMINANCE[type], type).toBe(variant)
		}
	})

	it('paints both siblings of a pair through one component', () => {
		expect(BACKGROUND_RENDERER['clouds-dark']).toBe(BACKGROUND_RENDERER.clouds)
		expect(BACKGROUND_RENDERER['darkveil-light']).toBe(BACKGROUND_RENDERER.darkveil)
		expect(BACKGROUND_RENDERER['sparkles-dark']).toBe(BACKGROUND_RENDERER.sparkles)
		expect(BACKGROUND_RENDERER['perlin-flow-light']).toBe(BACKGROUND_RENDERER['perlin-flow'])
	})
})

describe('variant palettes', () => {
	it('leaves the wallpaper as designed in the theme it was built for', () => {
		// dark natives
		expect(BACKGROUND_DEFAULTS.darkveil.darkveilTintColor).toBe('#ffffff')
		expect(BACKGROUND_DEFAULTS.darkveil.darkveilBackgroundColor).toBe('#000000')
		expect(BACKGROUND_DEFAULTS.lightrays.raysBackgroundColor).toBe('#000000')
		expect(BACKGROUND_DEFAULTS.silk.silkColor).toBe('#3b3541')
		expect(BACKGROUND_DEFAULTS.embers.embersBackgroundColor).toBe('#1a1a2e')
		// light natives
		expect(BACKGROUND_DEFAULTS.clouds.cloudsSkyColor).toBe(0x68b8d7)
		expect(BACKGROUND_DEFAULTS.dots.dotsBackgroundColor).toBe('#f0ebe3')
		expect(BACKGROUND_DEFAULTS.sparkles.sparklesBackgroundColor).toBe('#fff0f5')
		// the pair that shipped before variants existed keeps its exact palette
		expect(BACKGROUND_DEFAULTS['clouds-dark'].cloudsSkyColor).toBe(0x0)
		expect(BACKGROUND_DEFAULTS['clouds-dark'].cloudsSpeed).toBe(0.31)
		expect(BACKGROUND_DEFAULTS['clouds2-dark'].clouds2BackgroundColor).toBe(0x0a1628)
		expect(BACKGROUND_DEFAULTS['clouds2-dark'].clouds2Speed).toBe(0.8)
	})

	it('lifts the hardcoded galaxy and silk palettes into params that keep the old look', () => {
		// mix(black, white, mass) and mix(black, color, pattern) reduce to the originals
		expect(BACKGROUND_DEFAULTS.galaxy.galaxyBackgroundColor).toBe('#000000')
		expect(BACKGROUND_DEFAULTS.galaxy.galaxyStarColor).toBe('#ffffff')
		expect(BACKGROUND_DEFAULTS.silk.silkBackgroundColor).toBe('#000000')
	})

	it('changes only colors between siblings, never the motion or shape params', () => {
		const structural = ['galaxyDensity', 'galaxySpeed', 'galaxyRotationSpeed'] as const
		for (const key of structural) {
			expect(BACKGROUND_DEFAULTS['galaxy-light'][key]).toBe(BACKGROUND_DEFAULTS.galaxy[key])
		}
		expect(BACKGROUND_DEFAULTS['dots-dark'].dotsSpacing).toBe(
			BACKGROUND_DEFAULTS.dots.dotsSpacing
		)
		expect(BACKGROUND_DEFAULTS['rain-light'].rainMaxDrops).toBe(
			BACKGROUND_DEFAULTS.rain.rainMaxDrops
		)
	})

	it('gives each light sibling a light field and each dark sibling a dark one', () => {
		expect(BACKGROUND_DEFAULTS['galaxy-light'].galaxyBackgroundColor).toBe('#eef0f7')
		expect(BACKGROUND_DEFAULTS['silk-light'].silkBackgroundColor).toBe('#f3f1f7')
		expect(BACKGROUND_DEFAULTS['rain-light'].rainBackgroundColor).toBe('#dde5ee')
		expect(BACKGROUND_DEFAULTS['dots-dark'].dotsBackgroundColor).toBe('#141310')
		expect(BACKGROUND_DEFAULTS['sparkles-dark'].sparklesBackgroundColor).toBe('#1a0f16')
	})
})
