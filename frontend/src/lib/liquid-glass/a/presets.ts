import type { GlassPreset } from './types'

const SPRING = { stiffness: 0.12, damping: 0.7 }

export const glassPresets: Record<string, GlassPreset> = {
	subtle: {
		base: {
			blur: 0.5,
			refractiveIndex: 1.1,
			specularOpacity: 0.3,
			glassThickness: 60,
			bezelWidth: 0.5,
		},
		hover: { blur: 1.5, refractiveIndex: 1.8, specularOpacity: 0.5 },
		spring: SPRING,
	},

	standard: {
		base: {
			blur: 1,
			refractiveIndex: 1.4,
			specularOpacity: 0.6,
			glassThickness: 110,
			bezelWidth: 1,
		},
		hover: { blur: 2.5, refractiveIndex: 3, specularOpacity: 0.9 },
		spring: SPRING,
	},

	heavy: {
		base: {
			blur: 3,
			refractiveIndex: 2,
			specularOpacity: 0.8,
			glassThickness: 160,
			bezelWidth: 2,
		},
		hover: { blur: 5, refractiveIndex: 4, specularOpacity: 1 },
		spring: SPRING,
	},

	nav: {
		base: {
			blur: 0,
			refractiveIndex: 1.4,
			specularOpacity: 0.9,
			glassThickness: 110,
			bezelWidth: 1.5,
		},
		hover: { blur: 1.5, refractiveIndex: 3 },
		spring: SPRING,
	},

	panel: {
		base: {
			blur: 0,
			refractiveIndex: 1.4,
			specularOpacity: 0.9,
			glassThickness: 110,
			bezelWidth: 1.5,
		},
		hover: { blur: 0.8, refractiveIndex: 2 },
		focus: { blur: 3.5, refractiveIndex: 3 },
		spring: SPRING,
	},
} satisfies Record<string, GlassPreset>
