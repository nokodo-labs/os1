/**
 * centralized default configs for every background/wallpaper type.
 *
 * edit values here to change the default appearance for ALL users when
 * they pick a wallpaper and have not stored a custom config override.
 *
 * colors for vanta-based backgrounds use hex numbers (e.g. 0x68b8d7).
 * colors for shader-based backgrounds use hex strings (e.g. '#FF9FFC').
 */

import type { BackgroundConfig, BackgroundType } from './BackgroundManager.svelte'

export const BACKGROUND_DEFAULTS: Record<BackgroundType, BackgroundConfig> = {
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

	// ── clouds dark (night / dark mode) ──────────────────
	'clouds-dark': {
		cloudsSkyColor: 0x0,
		cloudsCloudColor: 0x403b3b,
		cloudsCloudShadowColor: 0x6e6363,
		cloudsSunColor: 0x50505,
		cloudsSunGlareColor: 0xc8a3ff,
		cloudsSunlightColor: 0xe733ff,
		cloudsSpeed: 0.31,
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

	// ── clouds 2 dark (night / dark mode) ────────────────
	'clouds2-dark': {
		clouds2SkyColor: 0x0d1b3e,
		clouds2CloudColor: 0x1e3a5f,
		clouds2LightColor: 0x324e7a,
		clouds2BackgroundColor: 0x0a1628,
		clouds2Scale: 1,
		clouds2Speed: 0.8,
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

	static: {
		color: '#171717',
	},

	none: {},
}
