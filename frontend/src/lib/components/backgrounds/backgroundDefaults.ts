/**
 * centralized default configs for every background/wallpaper type.
 *
 * edit values here to change the default appearance for ALL users when
 * they pick a wallpaper and have not stored a custom config override.
 *
 * colors for vanta-based backgrounds use hex numbers (e.g. 0x68b8d7).
 * colors for shader-based backgrounds use hex strings (e.g. '#FF9FFC').
 *
 * most wallpapers ship as a light/dark pair, the way `clouds` / `clouds-dark`
 * always has: two independent, separately selectable wallpapers that share one
 * renderer and differ only in palette. `BASE_DEFAULTS` holds the wallpaper as
 * it was designed, and its sibling spreads that and overrides the colors, so
 * tuning a shared parameter never has to be done twice.
 */

import type { BackgroundConfig, BackgroundType } from './BackgroundManager.svelte'

/** the wallpaper renderers - one per component, shared by both siblings of a pair */
export type BackgroundRenderer =
	| 'galaxy'
	| 'darkveil'
	| 'lightbends'
	| 'lightrays'
	| 'silk'
	| 'fog'
	| 'clouds'
	| 'clouds2'
	| 'grainient'
	| 'iridescence'
	| 'asciiorb'
	| 'lensgrain'
	| 'dither'
	| 'orbglow'
	| 'dots'
	| 'synapse'
	| 'rain'
	| 'constellations'
	| 'perlin-flow'
	| 'petals'
	| 'sparkles'
	| 'embers'
	| 'static'
	| 'none'

/** which theme a wallpaper's palette was built for */
export type BackgroundVariant = 'light' | 'dark'

// the wallpaper as designed; each entry is one renderer's own palette
const BASE_DEFAULTS = {
	galaxy: {
		galaxyFocalX: 0.5,
		galaxyFocalY: 0.5,
		galaxyRotationX: 1.0,
		galaxyRotationY: 0.0,
		galaxyStarSpeed: 0.5,
		galaxyDensity: 1.0,
		galaxySpeed: 1.0,
		galaxyGlowIntensity: 0.3,
		galaxyTwinkleIntensity: 0.3,
		galaxyRotationSpeed: 0.1,
		galaxyBackgroundColor: '#000000',
		galaxyStarColor: '#ffffff',
	},

	darkveil: {
		darkveilHueShift: 0,
		darkveilNoiseIntensity: 0,
		darkveilScanlineIntensity: 0,
		darkveilSpeed: 0.5,
		darkveilScanlineFrequency: 0,
		darkveilWarpAmount: 0,
		darkveilResolutionScale: 1,
		darkveilTintColor: '#ffffff',
		darkveilBackgroundColor: '#000000',
	},

	lightbends: {
		lightBendsColors: ['#212121', '#000000', '#342d43'],
		lightBendsSpeed: 0.1,
		lightBendsWarp: 1,
		lightBendsRotation: 45,
		lightBendsAutoRotate: 0.3,
		lightBendsScale: 1,
		lightBendsFrequency: 1,
		lightBendsMouseInfluence: 0,
		lightBendsParallax: 0,
		lightBendsNoise: 0,
	},

	lightrays: {
		raysOrigin: 'top-center',
		raysColor: '#ffffff',
		raysBackgroundColor: '#000000',
		raysSpeed: 0.5,
		raysLightSpread: 0.8,
		raysRayLength: 3.8,
		raysPulsating: false,
		raysFadeDistance: 3.8,
		raysSaturation: 0.6,
		raysFollowMouse: false,
		raysMouseInfluence: 0.5,
		raysNoiseAmount: 0.0,
		raysDistortion: 0.01,
	},

	silk: {
		silkColor: '#3b3541',
		silkBackgroundColor: '#000000',
		silkSpeed: 0.8,
	},

	fog: {
		fogHighlightColor: 0xd4bbff,
		fogMidtoneColor: 0x6633cc,
		fogLowlightColor: 0x220044,
		fogBaseColor: 0x0a0010,
		fogBlurFactor: 0.6,
		fogSpeed: 0.5,
		fogZoom: 0.8,
		fogMouseControls: false,
		fogTouchControls: false,
		fogGyroControls: false,
		fogMinHeight: 200,
		fogMinWidth: 200,
	},

	// ── clouds (light / day) ──────────────────────────────
	clouds: {
		cloudsSkyColor: 0x68b8d7,
		cloudsCloudColor: 0xffffff,
		cloudsCloudShadowColor: 0x374b6b,
		cloudsSunColor: 0xff9999,
		cloudsSunGlareColor: 0x88bbff,
		cloudsSunlightColor: 0xff9988,
		cloudsSpeed: 1,
		cloudsMouseControls: false,
		cloudsTouchControls: false,
		cloudsGyroControls: false,
		cloudsMinHeight: 200,
		cloudsMinWidth: 200,
	},

	// ── clouds 2 (light / day) ────────────────────────────
	clouds2: {
		clouds2SkyColor: 0xbfdff7,
		clouds2CloudColor: 0xeef4fa,
		clouds2LightColor: 0xffffff,
		clouds2BackgroundColor: 0x89bbdc,
		clouds2Scale: 1,
		clouds2Speed: 1,
		clouds2TexturePath: '/backgrounds/noise.png',
		clouds2MouseControls: true,
		clouds2TouchControls: true,
		clouds2GyroControls: false,
		clouds2MinHeight: 200,
		clouds2MinWidth: 200,
	},

	// ── grainient (OGL shader gradient) ──────────────────
	grainient: {
		grainientTimeSpeed: 0.25,
		grainientColorBalance: 0.0,
		grainientWarpStrength: 1.0,
		grainientWarpFrequency: 5.0,
		grainientWarpSpeed: 2.0,
		grainientWarpAmplitude: 50.0,
		grainientBlendAngle: 0.0,
		grainientBlendSoftness: 0.05,
		grainientRotationAmount: 500.0,
		grainientNoiseScale: 2.0,
		grainientGrainAmount: 0.1,
		grainientGrainScale: 2.0,
		grainientGrainAnimated: false,
		grainientContrast: 1.5,
		grainientGamma: 1.0,
		grainientSaturation: 1.0,
		grainientCenterX: 0.0,
		grainientCenterY: 0.0,
		grainientZoom: 0.9,
		grainientColor1: '#FF9FFC',
		grainientColor2: '#5227FF',
		grainientColor3: '#B19EEF',
	},

	// ── iridescence (OGL shader) ──────────────────────────
	iridescence: {
		iridescenceColor: [1, 1, 1],
		iridescenceSpeed: 1.0,
		iridescenceAmplitude: 0.1,
		iridescenceMouseReact: true,
	},

	// ── ascii orb (canvas 2d, ported from hermes) ────────
	asciiorb: {
		asciiOrbColor: '#ffe6cb',
		asciiOrbBackgroundColor: '#041c1c',
		asciiOrbFontSize: 8,
		asciiOrbRadius: 0.135,
		asciiOrbZoom: 3,
		asciiOrbSpin: 0.18,
		asciiOrbTilt: 0.55,
		asciiOrbWire: 0.2,
		asciiOrbLatitudes: 19,
		asciiOrbLongitudes: 30,
		asciiOrbShape: 'sphere',
		asciiOrbCubeScale: 1.8,
		asciiOrbMorphDuration: 0.65,
		asciiOrbBuildDuration: 1.45,
	},

	// ── lens grain (webgl film grain, ported from hermes) ─
	lensgrain: {
		lensGrainColor: '#eaeaea',
		lensGrainBackgroundColor: '#041c1c',
		lensGrainDensity: 0.11,
		lensGrainOpacity: 0.25,
		lensGrainSize: 1,
		lensGrainAnimated: true,
		lensGrainVignetteColor: '#ffbd38',
		lensGrainVignetteOpacity: 0.22,
	},

	// ── dither (static css halftone, ported from hermes) ──
	dither: {
		ditherColor: '#170d02',
		ditherAccentColor: '#ffac02',
		ditherGlowStrength: 6,
		ditherGlowSpread: 55,
		ditherDotStrength: 4,
		ditherDotSize: 3,
	},

	// ── orb glow (css radial glow, ported from hermes) ────
	orbglow: {
		orbGlowColor: '#ffc878',
		orbGlowHaloColor: '#ff8c50',
		orbGlowBackgroundColor: '#0c0d10',
		orbGlowCoreOpacity: 0.35,
		orbGlowHaloOpacity: 0.1,
		orbGlowRadius: 45,
		orbGlowFollowPointer: true,
		orbGlowDrift: 0.06,
		orbGlowEasing: 4,
	},

	// odysseus ports - each default reproduces the theme that shipped the pattern:
	// dots/light, synapse/cyberpunk, rain/midnight, constellations/ocean,
	// perlin-flow/terminal, petals/ume, sparkles/cute, embers/retrowave

	dots: {
		dotsColor: '#5a5248',
		dotsBackgroundColor: '#f0ebe3',
		dotsIntensity: 1,
		dotsSpacing: 20,
		dotsStrength: 5,
		dotsDotSize: 1,
	},

	synapse: {
		synapseColor: '#0ff0fc',
		synapseBackgroundColor: '#0a0a0f',
		synapseIntensity: 1,
		synapseGrid: 24,
		synapseGridStrength: 3.5,
		synapseMaxPulses: 20,
		synapseSpawnChance: 0.12,
		synapseSpeedMin: 2,
		synapseSpeedMax: 22,
		synapseTrailLength: 12,
	},

	rain: {
		rainColor: '#ffffff',
		rainBackgroundColor: '#0d1117',
		rainIntensity: 0.5,
		rainSize: 1,
		rainMaxDrops: 130,
		rainSpawnChance: 0.6,
	},

	constellations: {
		constellationsColor: '#64d2ff',
		constellationsBackgroundColor: '#0b1a2c',
		constellationsIntensity: 1,
		constellationsStarCount: 50,
		constellationsConnectDistance: 120,
		constellationsDriftSpeed: 0.15,
		constellationsTwinkleSpeed: 0.01,
	},

	'perlin-flow': {
		perlinFlowColor: '#00ff41',
		perlinFlowBackgroundColor: '#000000',
		perlinFlowIntensity: 0.8,
		perlinFlowParticleCount: 200,
		perlinFlowFadeAlpha: 0.02,
		perlinFlowNoiseScale: 0.004,
		perlinFlowTimeScale: 0.0008,
		perlinFlowSpeed: 1,
		perlinFlowDotRadius: 1,
		perlinFlowLifeDecay: 0.001,
	},

	petals: {
		petalsColor: '#f5a0c0',
		petalsBackgroundColor: '#2b1b2e',
		petalsIntensity: 1,
		petalsSize: 1,
		petalsCount: 30,
		petalsFallSpeed: 1,
	},

	sparkles: {
		sparklesColor: '#ff8cb8',
		sparklesBackgroundColor: '#fff0f5',
		sparklesIntensity: 1,
		sparklesSize: 1,
		sparklesCount: 35,
		sparklesTwinkleSpeed: 1,
	},

	embers: {
		embersColor: '#e94560',
		embersBackgroundColor: '#1a1a2e',
		embersIntensity: 1,
		embersSize: 1,
		embersCount: 60,
		embersFadeAlpha: 0.18,
		embersSparkChance: 0.003,
		embersBurstChance: 0.015,
		embersBurstSize: 5,
	},

	static: {
		color: '#171717',
	},

	none: {},
} satisfies Record<BackgroundRenderer, BackgroundConfig>

export const BACKGROUND_DEFAULTS: Record<BackgroundType, BackgroundConfig> = {
	...BASE_DEFAULTS,

	// ── light siblings of the dark-native wallpapers ──────

	'galaxy-light': {
		...BASE_DEFAULTS.galaxy,
		galaxyBackgroundColor: '#eef0f7',
		galaxyStarColor: '#2b3350',
	},

	'darkveil-light': {
		...BASE_DEFAULTS.darkveil,
		darkveilTintColor: '#3f3856',
		darkveilBackgroundColor: '#dcd8ea',
	},

	'lightbends-light': {
		...BASE_DEFAULTS.lightbends,
		lightBendsColors: ['#e9e6f2', '#ffffff', '#d5cee6'],
	},

	'lightrays-light': {
		...BASE_DEFAULTS.lightrays,
		raysColor: '#ffffff',
		raysBackgroundColor: '#cfd8ea',
	},

	'silk-light': {
		...BASE_DEFAULTS.silk,
		silkColor: '#cfc7dd',
		silkBackgroundColor: '#f3f1f7',
	},

	'fog-light': {
		...BASE_DEFAULTS.fog,
		fogHighlightColor: 0xffffff,
		fogMidtoneColor: 0xcdd9f2,
		fogLowlightColor: 0xa9bce0,
		fogBaseColor: 0xeef2fa,
	},

	'asciiorb-light': {
		...BASE_DEFAULTS.asciiorb,
		asciiOrbColor: '#3b3a36',
		asciiOrbBackgroundColor: '#f4f1e8',
	},

	'lensgrain-light': {
		...BASE_DEFAULTS.lensgrain,
		lensGrainColor: '#3f3b34',
		lensGrainBackgroundColor: '#f2efe8',
		lensGrainVignetteColor: '#c08a2e',
	},

	'dither-light': {
		...BASE_DEFAULTS.dither,
		ditherColor: '#f1ead9',
		ditherAccentColor: '#b8770d',
	},

	'orbglow-light': {
		...BASE_DEFAULTS.orbglow,
		orbGlowColor: '#ff9d3d',
		orbGlowHaloColor: '#ff7a45',
		orbGlowBackgroundColor: '#f5f0e8',
		orbGlowCoreOpacity: 0.3,
		orbGlowHaloOpacity: 0.12,
	},

	'synapse-light': {
		...BASE_DEFAULTS.synapse,
		synapseColor: '#0e7490',
		synapseBackgroundColor: '#eef4f8',
	},

	'rain-light': {
		...BASE_DEFAULTS.rain,
		rainColor: '#5d6b80',
		rainBackgroundColor: '#dde5ee',
	},

	'constellations-light': {
		...BASE_DEFAULTS.constellations,
		constellationsColor: '#2f6ea8',
		constellationsBackgroundColor: '#e6eef7',
	},

	'perlin-flow-light': {
		...BASE_DEFAULTS['perlin-flow'],
		perlinFlowColor: '#1f7a3d',
		perlinFlowBackgroundColor: '#f1f5ef',
	},

	'petals-light': {
		...BASE_DEFAULTS.petals,
		petalsColor: '#e07aa4',
		petalsBackgroundColor: '#fdf1f5',
	},

	'embers-light': {
		...BASE_DEFAULTS.embers,
		embersColor: '#d1462f',
		embersBackgroundColor: '#f8efe6',
	},

	// ── dark siblings of the light-native wallpapers ──────

	'clouds-dark': {
		...BASE_DEFAULTS.clouds,
		cloudsSkyColor: 0x0,
		cloudsCloudColor: 0x403b3b,
		cloudsCloudShadowColor: 0x6e6363,
		cloudsSunColor: 0x50505,
		cloudsSunGlareColor: 0xc8a3ff,
		cloudsSunlightColor: 0xe733ff,
		cloudsSpeed: 0.31,
	},

	'clouds2-dark': {
		...BASE_DEFAULTS.clouds2,
		clouds2SkyColor: 0x0d1b3e,
		clouds2CloudColor: 0x1e3a5f,
		clouds2LightColor: 0x324e7a,
		clouds2BackgroundColor: 0x0a1628,
		clouds2Speed: 0.8,
	},

	'grainient-dark': {
		...BASE_DEFAULTS.grainient,
		grainientColor1: '#7a2f8f',
		grainientColor2: '#0b0620',
		grainientColor3: '#2f2a6b',
	},

	'iridescence-dark': {
		...BASE_DEFAULTS.iridescence,
		iridescenceColor: [0.22, 0.2, 0.34],
	},

	'dots-dark': {
		...BASE_DEFAULTS.dots,
		dotsColor: '#6b6459',
		dotsBackgroundColor: '#141310',
	},

	'sparkles-dark': {
		...BASE_DEFAULTS.sparkles,
		sparklesColor: '#ffb3d2',
		sparklesBackgroundColor: '#1a0f16',
	},
}

/** every wallpaper, both siblings of each light/dark pair next to each other */
export const BACKGROUND_TYPES: readonly BackgroundType[] = [
	'galaxy',
	'galaxy-light',
	'darkveil',
	'darkveil-light',
	'lightbends',
	'lightbends-light',
	'lightrays',
	'lightrays-light',
	'silk',
	'silk-light',
	'fog',
	'fog-light',
	'clouds',
	'clouds-dark',
	'clouds2',
	'clouds2-dark',
	'grainient',
	'grainient-dark',
	'iridescence',
	'iridescence-dark',
	'asciiorb',
	'asciiorb-light',
	'lensgrain',
	'lensgrain-light',
	'dither',
	'dither-light',
	'orbglow',
	'orbglow-light',
	'dots',
	'dots-dark',
	'synapse',
	'synapse-light',
	'rain',
	'rain-light',
	'constellations',
	'constellations-light',
	'perlin-flow',
	'perlin-flow-light',
	'petals',
	'petals-light',
	'sparkles',
	'sparkles-dark',
	'embers',
	'embers-light',
	'static',
	'none',
]

/** which component paints a wallpaper - both siblings of a pair share one */
export const BACKGROUND_RENDERER: Record<BackgroundType, BackgroundRenderer> = {
	galaxy: 'galaxy',
	'galaxy-light': 'galaxy',
	darkveil: 'darkveil',
	'darkveil-light': 'darkveil',
	lightbends: 'lightbends',
	'lightbends-light': 'lightbends',
	lightrays: 'lightrays',
	'lightrays-light': 'lightrays',
	silk: 'silk',
	'silk-light': 'silk',
	fog: 'fog',
	'fog-light': 'fog',
	clouds: 'clouds',
	'clouds-dark': 'clouds',
	clouds2: 'clouds2',
	'clouds2-dark': 'clouds2',
	grainient: 'grainient',
	'grainient-dark': 'grainient',
	iridescence: 'iridescence',
	'iridescence-dark': 'iridescence',
	asciiorb: 'asciiorb',
	'asciiorb-light': 'asciiorb',
	lensgrain: 'lensgrain',
	'lensgrain-light': 'lensgrain',
	dither: 'dither',
	'dither-light': 'dither',
	orbglow: 'orbglow',
	'orbglow-light': 'orbglow',
	dots: 'dots',
	'dots-dark': 'dots',
	synapse: 'synapse',
	'synapse-light': 'synapse',
	rain: 'rain',
	'rain-light': 'rain',
	constellations: 'constellations',
	'constellations-light': 'constellations',
	'perlin-flow': 'perlin-flow',
	'perlin-flow-light': 'perlin-flow',
	petals: 'petals',
	'petals-light': 'petals',
	sparkles: 'sparkles',
	'sparkles-dark': 'sparkles',
	embers: 'embers',
	'embers-light': 'embers',
	static: 'static',
	none: 'none',
}

/**
 * which theme each wallpaper's palette was built for. selection stays manual -
 * this is a tag a rotation pool can filter on, not a resolver input.
 *
 * `static` and `none` are null: static paints whatever color the user picked,
 * and none paints nothing, so neither has a light/dark pair to tag.
 */
export const BACKGROUND_VARIANT: Record<BackgroundType, BackgroundVariant | null> = {
	galaxy: 'dark',
	'galaxy-light': 'light',
	darkveil: 'dark',
	'darkveil-light': 'light',
	lightbends: 'dark',
	'lightbends-light': 'light',
	lightrays: 'dark',
	'lightrays-light': 'light',
	silk: 'dark',
	'silk-light': 'light',
	fog: 'dark',
	'fog-light': 'light',
	clouds: 'light',
	'clouds-dark': 'dark',
	clouds2: 'light',
	'clouds2-dark': 'dark',
	grainient: 'light',
	'grainient-dark': 'dark',
	iridescence: 'light',
	'iridescence-dark': 'dark',
	asciiorb: 'dark',
	'asciiorb-light': 'light',
	lensgrain: 'dark',
	'lensgrain-light': 'light',
	dither: 'dark',
	'dither-light': 'light',
	orbglow: 'dark',
	'orbglow-light': 'light',
	dots: 'light',
	'dots-dark': 'dark',
	synapse: 'dark',
	'synapse-light': 'light',
	rain: 'dark',
	'rain-light': 'light',
	constellations: 'dark',
	'constellations-light': 'light',
	'perlin-flow': 'dark',
	'perlin-flow-light': 'light',
	petals: 'dark',
	'petals-light': 'light',
	sparkles: 'light',
	'sparkles-dark': 'dark',
	embers: 'dark',
	'embers-light': 'light',
	static: null,
	none: null,
}

/** which of black/white a background contrasts with more, used to match the theme */
export type BackgroundLuminance = 'dark' | 'light'

export const BACKGROUND_LUMINANCE: Record<BackgroundType, BackgroundLuminance> = {
	galaxy: 'dark',
	'galaxy-light': 'light',
	darkveil: 'dark',
	'darkveil-light': 'light',
	lightbends: 'dark',
	'lightbends-light': 'light',
	lightrays: 'dark',
	'lightrays-light': 'light',
	silk: 'dark',
	'silk-light': 'light',
	fog: 'dark',
	'fog-light': 'light',
	clouds: 'light',
	'clouds-dark': 'dark',
	clouds2: 'light',
	'clouds2-dark': 'dark',
	grainient: 'light',
	'grainient-dark': 'dark',
	iridescence: 'light',
	'iridescence-dark': 'dark',
	asciiorb: 'dark',
	'asciiorb-light': 'light',
	lensgrain: 'dark',
	'lensgrain-light': 'light',
	dither: 'dark',
	'dither-light': 'light',
	orbglow: 'dark',
	'orbglow-light': 'light',
	dots: 'light',
	'dots-dark': 'dark',
	synapse: 'dark',
	'synapse-light': 'light',
	rain: 'dark',
	'rain-light': 'light',
	constellations: 'dark',
	'constellations-light': 'light',
	'perlin-flow': 'dark',
	'perlin-flow-light': 'light',
	petals: 'dark',
	'petals-light': 'light',
	sparkles: 'light',
	'sparkles-dark': 'dark',
	embers: 'dark',
	'embers-light': 'light',
	static: 'dark', // overridden at runtime from the resolved static color
	none: 'dark',
}

/** convert one sRGB channel (0-1) to its linear-light value. */
function linearize(channel: number): number {
	return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
}

/**
 * decide whether a hex color contrasts more with black or with white,
 * via WCAG contrast ratios. returns 'dark' when the color pairs better with
 * white (so it wants a dark theme) and 'light' otherwise.
 */
export function colorLuminance(hex: string): BackgroundLuminance {
	const normalized = hex.replace('#', '')
	const full =
		normalized.length === 3
			? normalized
					.split('')
					.map((c) => c + c)
					.join('')
			: normalized
	if (full.length !== 6) return 'dark'
	const r = linearize(parseInt(full.slice(0, 2), 16) / 255)
	const g = linearize(parseInt(full.slice(2, 4), 16) / 255)
	const b = linearize(parseInt(full.slice(4, 6), 16) / 255)
	const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
	const contrastWithWhite = 1.05 / (luminance + 0.05)
	const contrastWithBlack = (luminance + 0.05) / 0.05
	return contrastWithWhite >= contrastWithBlack ? 'dark' : 'light'
}
