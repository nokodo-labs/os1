<script lang="ts">
	import { browser } from '$app/environment'
	import { resolve } from '$app/paths'
	import {
		BACKGROUND_DEFAULTS,
		BACKGROUND_RENDERER,
		BACKGROUND_TYPES,
		BACKGROUND_VARIANT,
		type BackgroundRenderer,
	} from '$lib/components/backgrounds/backgroundDefaults'
	import type {
		BackgroundConfig,
		BackgroundType,
	} from '$lib/components/backgrounds/BackgroundManager.svelte'
	import { DropdownSelect } from '$lib/components/primitives'
	import { background } from '$lib/stores/background.svelte'
	import { onDestroy } from 'svelte'

	const STORAGE_SELECTED = 'debug:backgrounds:selected'
	const STORAGE_CONFIG = 'debug:backgrounds:config'

	const backgroundOptions = BACKGROUND_TYPES.map((value) => ({
		value,
		label:
			BACKGROUND_VARIANT[value] === null ? value : `${value} (${BACKGROUND_VARIANT[value]})`,
	}))

	const asciiOrbShapes = ['sphere', 'cube'] as const

	const DEFAULT_CONFIG: BackgroundConfig = {
		color: '#171717',
		lightBendsColors: ['#ff0080', '#0080ff', '#00ff80'],
		lightBendsSpeed: 0.2,
		lightBendsWarp: 1,
		lightBendsRotation: 45,
		lightBendsAutoRotate: 0,
		lightBendsScale: 1,
		lightBendsFrequency: 1,
		lightBendsMouseInfluence: 1,
		lightBendsParallax: 0.5,
		lightBendsNoise: 0.1,
		raysOrigin: 'top-center',
		raysColor: '#ffffff',
		raysBackgroundColor: '#000000',
		raysSpeed: 1,
		raysLightSpread: 0.5,
		raysRayLength: 1.0,
		raysPulsating: false,
		raysFadeDistance: 1.0,
		raysSaturation: 1.0,
		raysFollowMouse: false,
		raysMouseInfluence: 0.5,
		raysNoiseAmount: 0.0,
		raysDistortion: 0.0,
		silkColor: '#7B7481',
		silkBackgroundColor: '#000000',
		silkSpeed: 5,
		darkveilHueShift: 0,
		darkveilNoiseIntensity: 0,
		darkveilScanlineIntensity: 0,
		darkveilSpeed: 0.5,
		darkveilScanlineFrequency: 0,
		darkveilWarpAmount: 0,
		darkveilResolutionScale: 1,
		darkveilTintColor: '#ffffff',
		darkveilBackgroundColor: '#000000',
		fogHighlightColor: 0xffc300,
		fogMidtoneColor: 0xff1f00,
		fogLowlightColor: 0x2d00ff,
		fogBaseColor: 0x0f091f,
		fogBlurFactor: 0.6,
		fogSpeed: 1,
		fogZoom: 1,
		fogMouseControls: true,
		fogTouchControls: true,
		fogGyroControls: false,
		fogMinHeight: 200,
		fogMinWidth: 200,
		cloudsSkyColor: 0x2d3e7f,
		cloudsCloudColor: 0xffffff,
		cloudsCloudShadowColor: 0x2f2f2f,
		cloudsSunColor: 0xffcc66,
		cloudsSunGlareColor: 0xff6633,
		cloudsSunlightColor: 0xff9933,
		cloudsSpeed: 1,
		cloudsMouseControls: true,
		cloudsTouchControls: true,
		cloudsGyroControls: false,
		cloudsMinHeight: 200,
		cloudsMinWidth: 200,
		clouds2Scale: 1,
		clouds2Speed: 1,
		clouds2TexturePath: '/backgrounds/noise.png',
		clouds2SkyColor: 0x68b8d7,
		clouds2CloudColor: 0xadc1de,
		clouds2LightColor: 0xffffff,
		clouds2BackgroundColor: 0x0,
		clouds2MouseControls: true,
		clouds2TouchControls: true,
		clouds2GyroControls: false,
		clouds2MinHeight: 200,
		clouds2MinWidth: 200,
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
		iridescenceColor: [1, 1, 1],
		iridescenceSpeed: 1.0,
		iridescenceAmplitude: 0.1,
		iridescenceMouseReact: true,
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
		lensGrainColor: '#eaeaea',
		lensGrainBackgroundColor: '#041c1c',
		lensGrainDensity: 0.11,
		lensGrainOpacity: 0.25,
		lensGrainSize: 1,
		lensGrainAnimated: true,
		lensGrainVignetteColor: '#ffbd38',
		lensGrainVignetteOpacity: 0.22,
		ditherColor: '#170d02',
		ditherAccentColor: '#ffac02',
		ditherGlowStrength: 6,
		ditherGlowSpread: 55,
		ditherDotStrength: 4,
		ditherDotSize: 3,
		orbGlowColor: '#ffc878',
		orbGlowHaloColor: '#ff8c50',
		orbGlowBackgroundColor: '#0c0d10',
		orbGlowCoreOpacity: 0.35,
		orbGlowHaloOpacity: 0.1,
		orbGlowRadius: 45,
		orbGlowFollowPointer: true,
		orbGlowDrift: 0.06,
		orbGlowEasing: 4,
		dotsColor: '#5a5248',
		dotsBackgroundColor: '#f0ebe3',
		dotsIntensity: 1,
		dotsSpacing: 20,
		dotsStrength: 5,
		dotsDotSize: 1,
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
		rainColor: '#ffffff',
		rainBackgroundColor: '#0d1117',
		rainIntensity: 0.5,
		rainSize: 1,
		rainMaxDrops: 130,
		rainSpawnChance: 0.6,
		constellationsColor: '#64d2ff',
		constellationsBackgroundColor: '#0b1a2c',
		constellationsIntensity: 1,
		constellationsStarCount: 50,
		constellationsConnectDistance: 120,
		constellationsDriftSpeed: 0.15,
		constellationsTwinkleSpeed: 0.01,
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
		petalsColor: '#f5a0c0',
		petalsBackgroundColor: '#2b1b2e',
		petalsIntensity: 1,
		petalsSize: 1,
		petalsCount: 30,
		petalsFallSpeed: 1,
		sparklesColor: '#ff8cb8',
		sparklesBackgroundColor: '#fff0f5',
		sparklesIntensity: 1,
		sparklesSize: 1,
		sparklesCount: 35,
		sparklesTwinkleSpeed: 1,
		embersColor: '#e94560',
		embersBackgroundColor: '#1a1a2e',
		embersIntensity: 1,
		embersSize: 1,
		embersCount: 60,
		embersFadeAlpha: 0.18,
		embersSparkChance: 0.003,
		embersBurstChance: 0.015,
		embersBurstSize: 5,
	}

	// keys belonging to each renderer - used to filter the output snippet
	const BG_KEYS: Record<BackgroundRenderer, (keyof BackgroundConfig)[]> = {
		galaxy: [
			'galaxyFocalX',
			'galaxyFocalY',
			'galaxyRotationX',
			'galaxyRotationY',
			'galaxyStarSpeed',
			'galaxyDensity',
			'galaxySpeed',
			'galaxyGlowIntensity',
			'galaxyTwinkleIntensity',
			'galaxyRotationSpeed',
			'galaxyBackgroundColor',
			'galaxyStarColor',
		],
		darkveil: [
			'darkveilHueShift',
			'darkveilNoiseIntensity',
			'darkveilScanlineIntensity',
			'darkveilSpeed',
			'darkveilScanlineFrequency',
			'darkveilWarpAmount',
			'darkveilResolutionScale',
			'darkveilTintColor',
			'darkveilBackgroundColor',
		],
		lightbends: [
			'lightBendsColors',
			'lightBendsSpeed',
			'lightBendsWarp',
			'lightBendsRotation',
			'lightBendsAutoRotate',
			'lightBendsScale',
			'lightBendsFrequency',
			'lightBendsMouseInfluence',
			'lightBendsParallax',
			'lightBendsNoise',
		],
		lightrays: [
			'raysOrigin',
			'raysColor',
			'raysBackgroundColor',
			'raysSpeed',
			'raysLightSpread',
			'raysRayLength',
			'raysPulsating',
			'raysFadeDistance',
			'raysSaturation',
			'raysFollowMouse',
			'raysMouseInfluence',
			'raysNoiseAmount',
			'raysDistortion',
		],
		silk: ['silkColor', 'silkBackgroundColor', 'silkSpeed'],
		fog: [
			'fogHighlightColor',
			'fogMidtoneColor',
			'fogLowlightColor',
			'fogBaseColor',
			'fogBlurFactor',
			'fogSpeed',
			'fogZoom',
			'fogMouseControls',
			'fogTouchControls',
			'fogGyroControls',
			'fogMinHeight',
			'fogMinWidth',
		],
		clouds: [
			'cloudsSkyColor',
			'cloudsCloudColor',
			'cloudsCloudShadowColor',
			'cloudsSunColor',
			'cloudsSunGlareColor',
			'cloudsSunlightColor',
			'cloudsSpeed',
			'cloudsMouseControls',
			'cloudsTouchControls',
			'cloudsGyroControls',
			'cloudsMinHeight',
			'cloudsMinWidth',
		],
		clouds2: [
			'clouds2SkyColor',
			'clouds2CloudColor',
			'clouds2LightColor',
			'clouds2BackgroundColor',
			'clouds2Scale',
			'clouds2Speed',
			'clouds2TexturePath',
			'clouds2MouseControls',
			'clouds2TouchControls',
			'clouds2GyroControls',
			'clouds2MinHeight',
			'clouds2MinWidth',
		],
		grainient: [
			'grainientTimeSpeed',
			'grainientColorBalance',
			'grainientWarpStrength',
			'grainientWarpFrequency',
			'grainientWarpSpeed',
			'grainientWarpAmplitude',
			'grainientBlendAngle',
			'grainientBlendSoftness',
			'grainientRotationAmount',
			'grainientNoiseScale',
			'grainientGrainAmount',
			'grainientGrainScale',
			'grainientGrainAnimated',
			'grainientContrast',
			'grainientGamma',
			'grainientSaturation',
			'grainientCenterX',
			'grainientCenterY',
			'grainientZoom',
			'grainientColor1',
			'grainientColor2',
			'grainientColor3',
		],
		iridescence: [
			'iridescenceColor',
			'iridescenceSpeed',
			'iridescenceAmplitude',
			'iridescenceMouseReact',
		],
		asciiorb: [
			'asciiOrbColor',
			'asciiOrbBackgroundColor',
			'asciiOrbFontSize',
			'asciiOrbRadius',
			'asciiOrbZoom',
			'asciiOrbSpin',
			'asciiOrbTilt',
			'asciiOrbWire',
			'asciiOrbLatitudes',
			'asciiOrbLongitudes',
			'asciiOrbShape',
			'asciiOrbCubeScale',
			'asciiOrbMorphDuration',
			'asciiOrbBuildDuration',
		],
		lensgrain: [
			'lensGrainColor',
			'lensGrainBackgroundColor',
			'lensGrainDensity',
			'lensGrainOpacity',
			'lensGrainSize',
			'lensGrainAnimated',
			'lensGrainVignetteColor',
			'lensGrainVignetteOpacity',
		],
		dither: [
			'ditherColor',
			'ditherAccentColor',
			'ditherGlowStrength',
			'ditherGlowSpread',
			'ditherDotStrength',
			'ditherDotSize',
		],
		orbglow: [
			'orbGlowColor',
			'orbGlowHaloColor',
			'orbGlowBackgroundColor',
			'orbGlowCoreOpacity',
			'orbGlowHaloOpacity',
			'orbGlowRadius',
			'orbGlowFollowPointer',
			'orbGlowDrift',
			'orbGlowEasing',
		],
		dots: [
			'dotsColor',
			'dotsBackgroundColor',
			'dotsIntensity',
			'dotsSpacing',
			'dotsStrength',
			'dotsDotSize',
		],
		synapse: [
			'synapseColor',
			'synapseBackgroundColor',
			'synapseIntensity',
			'synapseGrid',
			'synapseGridStrength',
			'synapseMaxPulses',
			'synapseSpawnChance',
			'synapseSpeedMin',
			'synapseSpeedMax',
			'synapseTrailLength',
		],
		rain: [
			'rainColor',
			'rainBackgroundColor',
			'rainIntensity',
			'rainSize',
			'rainMaxDrops',
			'rainSpawnChance',
		],
		constellations: [
			'constellationsColor',
			'constellationsBackgroundColor',
			'constellationsIntensity',
			'constellationsStarCount',
			'constellationsConnectDistance',
			'constellationsDriftSpeed',
			'constellationsTwinkleSpeed',
		],
		'perlin-flow': [
			'perlinFlowColor',
			'perlinFlowBackgroundColor',
			'perlinFlowIntensity',
			'perlinFlowParticleCount',
			'perlinFlowFadeAlpha',
			'perlinFlowNoiseScale',
			'perlinFlowTimeScale',
			'perlinFlowSpeed',
			'perlinFlowDotRadius',
			'perlinFlowLifeDecay',
		],
		petals: [
			'petalsColor',
			'petalsBackgroundColor',
			'petalsIntensity',
			'petalsSize',
			'petalsCount',
			'petalsFallSpeed',
		],
		sparkles: [
			'sparklesColor',
			'sparklesBackgroundColor',
			'sparklesIntensity',
			'sparklesSize',
			'sparklesCount',
			'sparklesTwinkleSpeed',
		],
		embers: [
			'embersColor',
			'embersBackgroundColor',
			'embersIntensity',
			'embersSize',
			'embersCount',
			'embersFadeAlpha',
			'embersSparkChance',
			'embersBurstChance',
			'embersBurstSize',
		],
		static: ['color'],
		none: [],
	}

	// keys whose numeric values should be formatted as 0xRRGGBB in the output snippet
	const HEX_COLOR_KEYS = new Set<keyof BackgroundConfig>([
		'fogHighlightColor',
		'fogMidtoneColor',
		'fogLowlightColor',
		'fogBaseColor',
		'cloudsSkyColor',
		'cloudsCloudColor',
		'cloudsCloudShadowColor',
		'cloudsSunColor',
		'cloudsSunGlareColor',
		'cloudsSunlightColor',
		'clouds2SkyColor',
		'clouds2CloudColor',
		'clouds2LightColor',
		'clouds2BackgroundColor',
	])

	let selected = $state<BackgroundType>('clouds2')
	let config = $state<BackgroundConfig>(DEFAULT_CONFIG)

	// both siblings of a pair share one renderer, so panels and the snippet key on it
	const renderer = $derived(BACKGROUND_RENDERER[selected])

	function isBackgroundType(value: string): value is BackgroundType {
		return BACKGROUND_TYPES.some((bg) => bg === value)
	}

	/** picking a wallpaper loads its own palette, so a variant shows as it ships */
	function selectBackground(value: string): void {
		if (!isBackgroundType(value)) return
		selected = value
		config = { ...config, ...BACKGROUND_DEFAULTS[value] }
	}

	if (browser) {
		const rawSelected = localStorage.getItem(STORAGE_SELECTED)
		if (rawSelected && isBackgroundType(rawSelected)) {
			selected = rawSelected
		}
		const rawConfig = localStorage.getItem(STORAGE_CONFIG)
		if (rawConfig) {
			try {
				const parsed = JSON.parse(rawConfig) as BackgroundConfig
				config = { ...DEFAULT_CONFIG, ...parsed }
			} catch {
				// ignore invalid local storage
			}
		}
	}

	$effect(() => {
		// a debug tool has to show every wallpaper, tier caps included
		background.setPage(selected, { allowAnimated: true })
	})

	$effect(() => {
		background.setPageConfig(config)
	})

	$effect(() => {
		if (!browser) return
		localStorage.setItem(STORAGE_SELECTED, selected)
		localStorage.setItem(STORAGE_CONFIG, JSON.stringify(config))
	})

	onDestroy(() => {
		background.clearPageConfig()
		background.clearPage()
	})

	const configSnippet = $derived.by(() => {
		const keys = BG_KEYS[renderer]
		if (keys.length === 0) return `'${selected}': {},`
		const lines = keys
			.filter((k) => config[k] !== undefined)
			.map((k) => {
				const v = config[k]
				let formatted: string
				if (HEX_COLOR_KEYS.has(k) && typeof v === 'number') {
					formatted = `0x${v.toString(16)}`
				} else if (typeof v === 'string') {
					formatted = `'${v}'`
				} else if (Array.isArray(v)) {
					formatted = `[${v.join(', ')}]`
				} else {
					formatted = String(v)
				}
				return `\t\t${k}: ${formatted},`
			})
			.join('\n')
		return `'${selected}': {\n${lines}\n\t},`
	})

	const raysOrigins = [
		'top-center',
		'top-left',
		'top-right',
		'right',
		'left',
		'bottom-center',
		'bottom-right',
		'bottom-left',
	] as const

	function toHex(value: number | undefined): string {
		if (value === undefined) return '#000000'
		const safe = Math.max(0, Math.min(0xffffff, value))
		return `#${safe.toString(16).padStart(6, '0')}`
	}

	function fromHex(value: string): number {
		return Number.parseInt(value.replace('#', ''), 16)
	}

	function setColor(key: keyof BackgroundConfig, value: string) {
		const next = fromHex(value)
		config = { ...config, [key]: next }
	}

	function setNumber(key: keyof BackgroundConfig, value: string) {
		const next = Number(value)
		if (!Number.isFinite(next)) return
		config = { ...config, [key]: next }
	}

	function setString(key: keyof BackgroundConfig, value: string) {
		config = { ...config, [key]: value }
	}

	function setBoolean(key: keyof BackgroundConfig, value: boolean) {
		config = { ...config, [key]: value }
	}

	function copyConfig() {
		if (!browser) return
		void navigator.clipboard.writeText(configSnippet)
	}

	function resetConfig() {
		if (!browser) return
		localStorage.removeItem(STORAGE_CONFIG)
		localStorage.removeItem(STORAGE_SELECTED)
		window.location.reload()
	}
</script>

<div class="mx-auto w-full max-w-3xl px-4 pt-8 pb-24 sm:px-6">
	<div class="space-y-2">
		<h1 class="text-xl font-semibold">backgrounds debug</h1>
		<p class="text-muted-foreground text-sm">
			tweaks the live app background. copy the snippet at the bottom and paste the object body
			into the matching key in <code>backgroundDefaults.ts</code>.
		</p>
	</div>

	<div class="mt-5 flex flex-wrap items-center gap-2">
		<a
			href={resolve('/debug')}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-3 py-1.5 text-sm transition"
		>
			back to debug
		</a>
		<button
			type="button"
			onclick={copyConfig}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-3 py-1.5 text-sm transition"
		>
			copy snippet
		</button>
		<button
			type="button"
			onclick={resetConfig}
			class="border-foreground/10 bg-foreground/5 text-foreground/80 hover:border-foreground/20 hover:bg-foreground/8 rounded-xl border px-3 py-1.5 text-sm transition"
		>
			reset
		</button>
	</div>

	<div class="mt-6 space-y-4">
		<div class="border-foreground/10 bg-foreground/5 rounded-2xl border p-4">
			<div class="text-foreground/60 mb-2 text-xs">background</div>
			<DropdownSelect
				options={backgroundOptions}
				value={selected}
				onchange={selectBackground}
				ariaLabel="background"
				buttonClass="rounded-lg px-3 py-2"
			/>
		</div>

		{#if renderer === 'static'}
			<div class="border-foreground/10 bg-foreground/5 rounded-2xl border p-4">
				<div class="text-foreground/60 mb-2 text-xs">color</div>
				<input
					type="color"
					value={config.color || '#171717'}
					oninput={(e) => setString('color', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'galaxy'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">focal X</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.galaxyFocalX ?? 0.5}
					oninput={(e) => setNumber('galaxyFocalX', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">focal Y</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.galaxyFocalY ?? 0.5}
					oninput={(e) => setNumber('galaxyFocalY', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">rotation X</div>
				<input
					type="range"
					min="-2"
					max="2"
					step="0.01"
					value={config.galaxyRotationX ?? 1.0}
					oninput={(e) => setNumber('galaxyRotationX', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">rotation Y</div>
				<input
					type="range"
					min="-2"
					max="2"
					step="0.01"
					value={config.galaxyRotationY ?? 0.0}
					oninput={(e) => setNumber('galaxyRotationY', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">star speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.galaxyStarSpeed ?? 0.5}
					oninput={(e) => setNumber('galaxyStarSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">density</div>
				<input
					type="range"
					min="0.1"
					max="4"
					step="0.05"
					value={config.galaxyDensity ?? 1.0}
					oninput={(e) => setNumber('galaxyDensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="4"
					step="0.05"
					value={config.galaxySpeed ?? 1.0}
					oninput={(e) => setNumber('galaxySpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">glow intensity</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.galaxyGlowIntensity ?? 0.3}
					oninput={(e) => setNumber('galaxyGlowIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">twinkle intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.galaxyTwinkleIntensity ?? 0.3}
					oninput={(e) => setNumber('galaxyTwinkleIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">rotation speed</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.005"
					value={config.galaxyRotationSpeed ?? 0.1}
					oninput={(e) => setNumber('galaxyRotationSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.galaxyBackgroundColor || '#000000'}
					oninput={(e) => setString('galaxyBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">star color</div>
				<input
					type="color"
					value={config.galaxyStarColor || '#ffffff'}
					oninput={(e) => setString('galaxyStarColor', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'darkveil'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">hue shift (deg)</div>
				<input
					type="range"
					min="-180"
					max="180"
					step="1"
					value={config.darkveilHueShift ?? 0}
					oninput={(e) => setNumber('darkveilHueShift', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.darkveilSpeed ?? 0.5}
					oninput={(e) => setNumber('darkveilSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp amount</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.darkveilWarpAmount ?? 0}
					oninput={(e) => setNumber('darkveilWarpAmount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">noise intensity</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.01"
					value={config.darkveilNoiseIntensity ?? 0}
					oninput={(e) => setNumber('darkveilNoiseIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">scanline intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.darkveilScanlineIntensity ?? 0}
					oninput={(e) => setNumber('darkveilScanlineIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">scanline frequency</div>
				<input
					type="range"
					min="0"
					max="20"
					step="0.1"
					value={config.darkveilScanlineFrequency ?? 0}
					oninput={(e) => setNumber('darkveilScanlineFrequency', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">resolution scale</div>
				<input
					type="range"
					min="0.25"
					max="2"
					step="0.05"
					value={config.darkveilResolutionScale ?? 1}
					oninput={(e) => setNumber('darkveilResolutionScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">tint color</div>
				<input
					type="color"
					value={config.darkveilTintColor || '#ffffff'}
					oninput={(e) => setString('darkveilTintColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.darkveilBackgroundColor || '#000000'}
					oninput={(e) => setString('darkveilBackgroundColor', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'lightbends'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lightBendsSpeed ?? 0.2}
					oninput={(e) => setNumber('lightBendsSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp strength</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.05"
					value={config.lightBendsWarp ?? 1}
					oninput={(e) => setNumber('lightBendsWarp', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">rotation (deg)</div>
				<input
					type="range"
					min="0"
					max="360"
					step="1"
					value={config.lightBendsRotation ?? 45}
					oninput={(e) => setNumber('lightBendsRotation', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">auto rotate speed</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.lightBendsAutoRotate ?? 0}
					oninput={(e) => setNumber('lightBendsAutoRotate', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">scale</div>
				<input
					type="range"
					min="0.1"
					max="4"
					step="0.05"
					value={config.lightBendsScale ?? 1}
					oninput={(e) => setNumber('lightBendsScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">frequency</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.05"
					value={config.lightBendsFrequency ?? 1}
					oninput={(e) => setNumber('lightBendsFrequency', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">mouse influence</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.05"
					value={config.lightBendsMouseInfluence ?? 1}
					oninput={(e) => setNumber('lightBendsMouseInfluence', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">parallax</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lightBendsParallax ?? 0.5}
					oninput={(e) => setNumber('lightBendsParallax', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">noise</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.005"
					value={config.lightBendsNoise ?? 0.1}
					oninput={(e) => setNumber('lightBendsNoise', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">colors</div>
				{#each config.lightBendsColors ?? ['#ff0080', '#0080ff', '#00ff80'] as color, i (i)}
					<div class="flex items-center gap-2">
						<span class="text-foreground/50 w-4 text-xs">{i + 1}</span>
						<input
							type="color"
							value={color}
							oninput={(e) => {
								const next = [
									...(config.lightBendsColors ?? [
										'#ff0080',
										'#0080ff',
										'#00ff80',
									]),
								]
								next[i] = e.currentTarget.value
								config = { ...config, lightBendsColors: next }
							}}
						/>
						<button
							type="button"
							class="text-foreground/40 hover:text-foreground/80 text-xs"
							onclick={() => {
								const next = (
									config.lightBendsColors ?? ['#ff0080', '#0080ff', '#00ff80']
								).filter((_, j) => j !== i)
								config = { ...config, lightBendsColors: next }
							}}>remove</button
						>
					</div>
				{/each}
				<button
					type="button"
					class="border-foreground/15 rounded-lg border px-3 py-1 text-xs"
					onclick={() => {
						config = {
							...config,
							lightBendsColors: [...(config.lightBendsColors ?? []), '#ffffff'],
						}
					}}>+ add color</button
				>
			</div>
		{:else if renderer === 'lightrays'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">origin</div>
				<DropdownSelect
					options={raysOrigins.map((origin) => ({ value: origin, label: origin }))}
					value={config.raysOrigin || 'top-center'}
					onchange={(value) => setString('raysOrigin', value)}
					ariaLabel="rays origin"
					buttonClass="rounded-lg px-3 py-2"
				/>
				<div class="text-foreground/60 text-xs">color</div>
				<input
					type="color"
					value={config.raysColor || '#ffffff'}
					oninput={(e) => setString('raysColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.05"
					value={config.raysSpeed || 1}
					oninput={(e) => setNumber('raysSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">light spread</div>
				<input
					type="range"
					min="0.05"
					max="1"
					step="0.01"
					value={config.raysLightSpread ?? 0.5}
					oninput={(e) => setNumber('raysLightSpread', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">ray length</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.05"
					value={config.raysRayLength ?? 1}
					oninput={(e) => setNumber('raysRayLength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">fade distance</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.05"
					value={config.raysFadeDistance ?? 1}
					oninput={(e) => setNumber('raysFadeDistance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">saturation</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.05"
					value={config.raysSaturation ?? 1}
					oninput={(e) => setNumber('raysSaturation', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">noise amount</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.01"
					value={config.raysNoiseAmount ?? 0}
					oninput={(e) => setNumber('raysNoiseAmount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">distortion</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.raysDistortion ?? 0}
					oninput={(e) => setNumber('raysDistortion', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">pulsating</div>
				<input
					type="checkbox"
					checked={config.raysPulsating ?? false}
					onchange={(e) => setBoolean('raysPulsating', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">follow mouse</div>
				<input
					type="checkbox"
					checked={config.raysFollowMouse ?? false}
					onchange={(e) => setBoolean('raysFollowMouse', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">mouse influence</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.raysMouseInfluence ?? 0.5}
					oninput={(e) => setNumber('raysMouseInfluence', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.raysBackgroundColor || '#000000'}
					oninput={(e) => setString('raysBackgroundColor', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'silk'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">color</div>
				<input
					type="color"
					value={config.silkColor || '#7B7481'}
					oninput={(e) => setString('silkColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.silkBackgroundColor || '#000000'}
					oninput={(e) => setString('silkBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="10"
					step="0.1"
					value={config.silkSpeed || 5}
					oninput={(e) => setNumber('silkSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'fog'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">mouse controls</div>
				<input
					type="checkbox"
					checked={config.fogMouseControls ?? true}
					onchange={(e) => setBoolean('fogMouseControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">touch controls</div>
				<input
					type="checkbox"
					checked={config.fogTouchControls ?? true}
					onchange={(e) => setBoolean('fogTouchControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">gyro controls</div>
				<input
					type="checkbox"
					checked={config.fogGyroControls ?? false}
					onchange={(e) => setBoolean('fogGyroControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.fogMinHeight ?? 200}
					oninput={(e) => setNumber('fogMinHeight', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.fogMinWidth ?? 200}
					oninput={(e) => setNumber('fogMinWidth', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">highlight color</div>
				<input
					type="color"
					value={toHex(config.fogHighlightColor)}
					oninput={(e) => setColor('fogHighlightColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">midtone color</div>
				<input
					type="color"
					value={toHex(config.fogMidtoneColor)}
					oninput={(e) => setColor('fogMidtoneColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">lowlight color</div>
				<input
					type="color"
					value={toHex(config.fogLowlightColor)}
					oninput={(e) => setColor('fogLowlightColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">base color</div>
				<input
					type="color"
					value={toHex(config.fogBaseColor)}
					oninput={(e) => setColor('fogBaseColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">blur factor</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.fogBlurFactor || 0.6}
					oninput={(e) => setNumber('fogBlurFactor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.fogSpeed || 1}
					oninput={(e) => setNumber('fogSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">zoom</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.01"
					value={config.fogZoom || 1}
					oninput={(e) => setNumber('fogZoom', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'clouds'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">mouse controls</div>
				<input
					type="checkbox"
					checked={config.cloudsMouseControls ?? true}
					onchange={(e) => setBoolean('cloudsMouseControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">touch controls</div>
				<input
					type="checkbox"
					checked={config.cloudsTouchControls ?? true}
					onchange={(e) => setBoolean('cloudsTouchControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">gyro controls</div>
				<input
					type="checkbox"
					checked={config.cloudsGyroControls ?? false}
					onchange={(e) => setBoolean('cloudsGyroControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.cloudsMinHeight ?? 200}
					oninput={(e) => setNumber('cloudsMinHeight', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.cloudsMinWidth ?? 200}
					oninput={(e) => setNumber('cloudsMinWidth', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">sky color</div>
				<input
					type="color"
					value={toHex(config.cloudsSkyColor)}
					oninput={(e) => setColor('cloudsSkyColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">cloud color</div>
				<input
					type="color"
					value={toHex(config.cloudsCloudColor)}
					oninput={(e) => setColor('cloudsCloudColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">cloud shadow color</div>
				<input
					type="color"
					value={toHex(config.cloudsCloudShadowColor)}
					oninput={(e) => setColor('cloudsCloudShadowColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">sun color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunColor)}
					oninput={(e) => setColor('cloudsSunColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">sun glare color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunGlareColor)}
					oninput={(e) => setColor('cloudsSunGlareColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">sunlight color</div>
				<input
					type="color"
					value={toHex(config.cloudsSunlightColor)}
					oninput={(e) => setColor('cloudsSunlightColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.cloudsSpeed || 1}
					oninput={(e) => setNumber('cloudsSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'clouds2'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">mouse controls</div>
				<input
					type="checkbox"
					checked={config.clouds2MouseControls ?? true}
					onchange={(e) => setBoolean('clouds2MouseControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">touch controls</div>
				<input
					type="checkbox"
					checked={config.clouds2TouchControls ?? true}
					onchange={(e) => setBoolean('clouds2TouchControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">gyro controls</div>
				<input
					type="checkbox"
					checked={config.clouds2GyroControls ?? false}
					onchange={(e) => setBoolean('clouds2GyroControls', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">min height</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.clouds2MinHeight ?? 200}
					oninput={(e) => setNumber('clouds2MinHeight', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">min width</div>
				<input
					type="number"
					min="1"
					step="1"
					value={config.clouds2MinWidth ?? 200}
					oninput={(e) => setNumber('clouds2MinWidth', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">texture path (empty disables noise)</div>
				<input
					class="border-foreground/15 w-full rounded-lg border bg-black/40 px-3 py-2 text-sm"
					type="text"
					value={config.clouds2TexturePath || ''}
					oninput={(e) => setString('clouds2TexturePath', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">scale</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.01"
					value={config.clouds2Scale || 1}
					oninput={(e) => setNumber('clouds2Scale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="3"
					step="0.01"
					value={config.clouds2Speed || 1}
					oninput={(e) => setNumber('clouds2Speed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">sky color</div>
				<input
					type="color"
					value={toHex(config.clouds2SkyColor)}
					oninput={(e) => setColor('clouds2SkyColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">cloud color</div>
				<input
					type="color"
					value={toHex(config.clouds2CloudColor)}
					oninput={(e) => setColor('clouds2CloudColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">light color</div>
				<input
					type="color"
					value={toHex(config.clouds2LightColor)}
					oninput={(e) => setColor('clouds2LightColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={toHex(config.clouds2BackgroundColor)}
					oninput={(e) => setColor('clouds2BackgroundColor', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'grainient'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">color 1</div>
				<input
					type="color"
					value={config.grainientColor1 || '#FF9FFC'}
					oninput={(e) => setString('grainientColor1', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">color 2</div>
				<input
					type="color"
					value={config.grainientColor2 || '#5227FF'}
					oninput={(e) => setString('grainientColor2', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">color 3</div>
				<input
					type="color"
					value={config.grainientColor3 || '#B19EEF'}
					oninput={(e) => setString('grainientColor3', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">time speed</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.grainientTimeSpeed ?? 0.25}
					oninput={(e) => setNumber('grainientTimeSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">color balance</div>
				<input
					type="range"
					min="-1"
					max="1"
					step="0.01"
					value={config.grainientColorBalance ?? 0}
					oninput={(e) => setNumber('grainientColorBalance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp strength</div>
				<input
					type="range"
					min="0.01"
					max="5"
					step="0.01"
					value={config.grainientWarpStrength ?? 1}
					oninput={(e) => setNumber('grainientWarpStrength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp frequency</div>
				<input
					type="range"
					min="0"
					max="20"
					step="0.1"
					value={config.grainientWarpFrequency ?? 5}
					oninput={(e) => setNumber('grainientWarpFrequency', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp speed</div>
				<input
					type="range"
					min="0"
					max="10"
					step="0.1"
					value={config.grainientWarpSpeed ?? 2}
					oninput={(e) => setNumber('grainientWarpSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">warp amplitude</div>
				<input
					type="range"
					min="1"
					max="200"
					step="1"
					value={config.grainientWarpAmplitude ?? 50}
					oninput={(e) => setNumber('grainientWarpAmplitude', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">blend angle</div>
				<input
					type="range"
					min="-180"
					max="180"
					step="1"
					value={config.grainientBlendAngle ?? 0}
					oninput={(e) => setNumber('grainientBlendAngle', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">blend softness</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.01"
					value={config.grainientBlendSoftness ?? 0.05}
					oninput={(e) => setNumber('grainientBlendSoftness', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">rotation amount</div>
				<input
					type="range"
					min="0"
					max="1000"
					step="1"
					value={config.grainientRotationAmount ?? 500}
					oninput={(e) => setNumber('grainientRotationAmount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">noise scale</div>
				<input
					type="range"
					min="0.1"
					max="10"
					step="0.1"
					value={config.grainientNoiseScale ?? 2}
					oninput={(e) => setNumber('grainientNoiseScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">grain amount</div>
				<input
					type="range"
					min="0"
					max="0.5"
					step="0.01"
					value={config.grainientGrainAmount ?? 0.1}
					oninput={(e) => setNumber('grainientGrainAmount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">grain scale</div>
				<input
					type="range"
					min="0.1"
					max="10"
					step="0.1"
					value={config.grainientGrainScale ?? 2}
					oninput={(e) => setNumber('grainientGrainScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">grain animated</div>
				<input
					type="checkbox"
					checked={config.grainientGrainAnimated ?? false}
					onchange={(e) => setBoolean('grainientGrainAnimated', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">contrast</div>
				<input
					type="range"
					min="0.5"
					max="3"
					step="0.01"
					value={config.grainientContrast ?? 1.5}
					oninput={(e) => setNumber('grainientContrast', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">gamma</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.01"
					value={config.grainientGamma ?? 1}
					oninput={(e) => setNumber('grainientGamma', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">saturation</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.01"
					value={config.grainientSaturation ?? 1}
					oninput={(e) => setNumber('grainientSaturation', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">center x</div>
				<input
					type="range"
					min="-0.5"
					max="0.5"
					step="0.01"
					value={config.grainientCenterX ?? 0}
					oninput={(e) => setNumber('grainientCenterX', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">center y</div>
				<input
					type="range"
					min="-0.5"
					max="0.5"
					step="0.01"
					value={config.grainientCenterY ?? 0}
					oninput={(e) => setNumber('grainientCenterY', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">zoom</div>
				<input
					type="range"
					min="0.1"
					max="3"
					step="0.01"
					value={config.grainientZoom ?? 0.9}
					oninput={(e) => setNumber('grainientZoom', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'iridescence'}
			{@const iColor = config.iridescenceColor ?? [1, 1, 1]}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">
					color r <span class="font-mono">{iColor[0].toFixed(2)}</span>
				</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={iColor[0]}
					oninput={(e) => {
						const c = config.iridescenceColor ?? [1, 1, 1]
						config = {
							...config,
							iridescenceColor: [Number(e.currentTarget.value), c[1], c[2]],
						}
					}}
				/>
				<div class="text-foreground/60 text-xs">
					color g <span class="font-mono">{iColor[1].toFixed(2)}</span>
				</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={iColor[1]}
					oninput={(e) => {
						const c = config.iridescenceColor ?? [1, 1, 1]
						config = {
							...config,
							iridescenceColor: [c[0], Number(e.currentTarget.value), c[2]],
						}
					}}
				/>
				<div class="text-foreground/60 text-xs">
					color b <span class="font-mono">{iColor[2].toFixed(2)}</span>
				</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={iColor[2]}
					oninput={(e) => {
						const c = config.iridescenceColor ?? [1, 1, 1]
						config = {
							...config,
							iridescenceColor: [c[0], c[1], Number(e.currentTarget.value)],
						}
					}}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0"
					max="5"
					step="0.05"
					value={config.iridescenceSpeed ?? 1}
					oninput={(e) => setNumber('iridescenceSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">amplitude</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.iridescenceAmplitude ?? 0.1}
					oninput={(e) => setNumber('iridescenceAmplitude', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">mouse react</div>
				<input
					type="checkbox"
					checked={config.iridescenceMouseReact ?? true}
					onchange={(e) => setBoolean('iridescenceMouseReact', e.currentTarget.checked)}
				/>
			</div>
		{:else if renderer === 'asciiorb'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">shape</div>
				<DropdownSelect
					options={asciiOrbShapes.map((shape) => ({ value: shape, label: shape }))}
					value={config.asciiOrbShape ?? 'sphere'}
					onchange={(value) => setString('asciiOrbShape', value)}
					ariaLabel="ascii orb shape"
					buttonClass="rounded-lg px-3 py-2"
				/>
				<div class="text-foreground/60 text-xs">glyph color</div>
				<input
					type="color"
					value={config.asciiOrbColor ?? '#ffe6cb'}
					oninput={(e) => setString('asciiOrbColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.asciiOrbBackgroundColor ?? '#041c1c'}
					oninput={(e) => setString('asciiOrbBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">font size</div>
				<input
					type="range"
					min="6"
					max="24"
					step="1"
					value={config.asciiOrbFontSize ?? 8}
					oninput={(e) => setNumber('asciiOrbFontSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">radius</div>
				<input
					type="range"
					min="0.05"
					max="0.4"
					step="0.005"
					value={config.asciiOrbRadius ?? 0.135}
					oninput={(e) => setNumber('asciiOrbRadius', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">zoom</div>
				<input
					type="range"
					min="0.25"
					max="12"
					step="0.05"
					value={config.asciiOrbZoom ?? 3}
					oninput={(e) => setNumber('asciiOrbZoom', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">spin</div>
				<input
					type="range"
					min="0"
					max="0.6"
					step="0.01"
					value={config.asciiOrbSpin ?? 0.18}
					oninput={(e) => setNumber('asciiOrbSpin', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">tilt</div>
				<input
					type="range"
					min="-1.5"
					max="1.5"
					step="0.01"
					value={config.asciiOrbTilt ?? 0.55}
					oninput={(e) => setNumber('asciiOrbTilt', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">wire</div>
				<input
					type="range"
					min="0.01"
					max="0.5"
					step="0.005"
					value={config.asciiOrbWire ?? 0.2}
					oninput={(e) => setNumber('asciiOrbWire', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">latitudes</div>
				<input
					type="range"
					min="4"
					max="60"
					step="1"
					value={config.asciiOrbLatitudes ?? 19}
					oninput={(e) => setNumber('asciiOrbLatitudes', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">longitudes</div>
				<input
					type="range"
					min="4"
					max="80"
					step="1"
					value={config.asciiOrbLongitudes ?? 30}
					oninput={(e) => setNumber('asciiOrbLongitudes', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">cube scale</div>
				<input
					type="range"
					min="0.8"
					max="3.5"
					step="0.01"
					value={config.asciiOrbCubeScale ?? 1.8}
					oninput={(e) => setNumber('asciiOrbCubeScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">morph duration</div>
				<input
					type="range"
					min="0.05"
					max="2"
					step="0.01"
					value={config.asciiOrbMorphDuration ?? 0.65}
					oninput={(e) => setNumber('asciiOrbMorphDuration', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">build duration</div>
				<input
					type="range"
					min="0.1"
					max="6"
					step="0.05"
					value={config.asciiOrbBuildDuration ?? 1.45}
					oninput={(e) => setNumber('asciiOrbBuildDuration', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'lensgrain'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">grain color</div>
				<input
					type="color"
					value={config.lensGrainColor ?? '#eaeaea'}
					oninput={(e) => setString('lensGrainColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.lensGrainBackgroundColor ?? '#041c1c'}
					oninput={(e) => setString('lensGrainBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">density</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lensGrainDensity ?? 0.11}
					oninput={(e) => setNumber('lensGrainDensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">opacity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lensGrainOpacity ?? 0.25}
					oninput={(e) => setNumber('lensGrainOpacity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">size</div>
				<input
					type="range"
					min="0.1"
					max="10"
					step="0.1"
					value={config.lensGrainSize ?? 1}
					oninput={(e) => setNumber('lensGrainSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">animated</div>
				<input
					type="checkbox"
					checked={config.lensGrainAnimated ?? true}
					onchange={(e) => setBoolean('lensGrainAnimated', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">vignette color</div>
				<input
					type="color"
					value={config.lensGrainVignetteColor ?? '#ffbd38'}
					oninput={(e) => setString('lensGrainVignetteColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">vignette opacity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.lensGrainVignetteOpacity ?? 0.22}
					oninput={(e) => setNumber('lensGrainVignetteOpacity', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'dither'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">base color</div>
				<input
					type="color"
					value={config.ditherColor ?? '#170d02'}
					oninput={(e) => setString('ditherColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">accent color</div>
				<input
					type="color"
					value={config.ditherAccentColor ?? '#ffac02'}
					oninput={(e) => setString('ditherAccentColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">glow strength (%)</div>
				<input
					type="range"
					min="0"
					max="40"
					step="0.5"
					value={config.ditherGlowStrength ?? 6}
					oninput={(e) => setNumber('ditherGlowStrength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">glow spread (%)</div>
				<input
					type="range"
					min="10"
					max="100"
					step="1"
					value={config.ditherGlowSpread ?? 55}
					oninput={(e) => setNumber('ditherGlowSpread', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">dot strength (%)</div>
				<input
					type="range"
					min="0"
					max="30"
					step="0.5"
					value={config.ditherDotStrength ?? 4}
					oninput={(e) => setNumber('ditherDotStrength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">dot size (px)</div>
				<input
					type="range"
					min="2"
					max="12"
					step="1"
					value={config.ditherDotSize ?? 3}
					oninput={(e) => setNumber('ditherDotSize', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'orbglow'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">core color</div>
				<input
					type="color"
					value={config.orbGlowColor ?? '#ffc878'}
					oninput={(e) => setString('orbGlowColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">halo color</div>
				<input
					type="color"
					value={config.orbGlowHaloColor ?? '#ff8c50'}
					oninput={(e) => setString('orbGlowHaloColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.orbGlowBackgroundColor ?? '#0c0d10'}
					oninput={(e) => setString('orbGlowBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">core opacity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.orbGlowCoreOpacity ?? 0.35}
					oninput={(e) => setNumber('orbGlowCoreOpacity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">halo opacity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.orbGlowHaloOpacity ?? 0.1}
					oninput={(e) => setNumber('orbGlowHaloOpacity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">radius (vmin)</div>
				<input
					type="range"
					min="10"
					max="120"
					step="1"
					value={config.orbGlowRadius ?? 45}
					oninput={(e) => setNumber('orbGlowRadius', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">follow pointer</div>
				<input
					type="checkbox"
					checked={config.orbGlowFollowPointer ?? true}
					onchange={(e) => setBoolean('orbGlowFollowPointer', e.currentTarget.checked)}
				/>
				<div class="text-foreground/60 text-xs">idle drift</div>
				<input
					type="range"
					min="0"
					max="0.4"
					step="0.005"
					value={config.orbGlowDrift ?? 0.06}
					oninput={(e) => setNumber('orbGlowDrift', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">easing</div>
				<input
					type="range"
					min="0.2"
					max="20"
					step="0.1"
					value={config.orbGlowEasing ?? 4}
					oninput={(e) => setNumber('orbGlowEasing', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'dots'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">dot color</div>
				<input
					type="color"
					value={config.dotsColor ?? '#5a5248'}
					oninput={(e) => setString('dotsColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.dotsBackgroundColor ?? '#f0ebe3'}
					oninput={(e) => setString('dotsBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.dotsIntensity ?? 1}
					oninput={(e) => setNumber('dotsIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">spacing (px)</div>
				<input
					type="range"
					min="6"
					max="80"
					step="1"
					value={config.dotsSpacing ?? 20}
					oninput={(e) => setNumber('dotsSpacing', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">strength (%)</div>
				<input
					type="range"
					min="0"
					max="40"
					step="0.5"
					value={config.dotsStrength ?? 5}
					oninput={(e) => setNumber('dotsStrength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">dot size (px)</div>
				<input
					type="range"
					min="0.5"
					max="6"
					step="0.5"
					value={config.dotsDotSize ?? 1}
					oninput={(e) => setNumber('dotsDotSize', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'synapse'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">pulse color</div>
				<input
					type="color"
					value={config.synapseColor ?? '#0ff0fc'}
					oninput={(e) => setString('synapseColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.synapseBackgroundColor ?? '#0a0a0f'}
					oninput={(e) => setString('synapseBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.synapseIntensity ?? 1}
					oninput={(e) => setNumber('synapseIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">grid size (px)</div>
				<input
					type="range"
					min="8"
					max="80"
					step="1"
					value={config.synapseGrid ?? 24}
					oninput={(e) => setNumber('synapseGrid', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">grid strength (%)</div>
				<input
					type="range"
					min="0"
					max="20"
					step="0.5"
					value={config.synapseGridStrength ?? 3.5}
					oninput={(e) => setNumber('synapseGridStrength', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">max pulses</div>
				<input
					type="range"
					min="1"
					max="120"
					step="1"
					value={config.synapseMaxPulses ?? 20}
					oninput={(e) => setNumber('synapseMaxPulses', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">spawn chance / frame</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.01"
					value={config.synapseSpawnChance ?? 0.12}
					oninput={(e) => setNumber('synapseSpawnChance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed min (px/frame)</div>
				<input
					type="range"
					min="0.5"
					max="30"
					step="0.5"
					value={config.synapseSpeedMin ?? 2}
					oninput={(e) => setNumber('synapseSpeedMin', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed max (px/frame)</div>
				<input
					type="range"
					min="0.5"
					max="60"
					step="0.5"
					value={config.synapseSpeedMax ?? 22}
					oninput={(e) => setNumber('synapseSpeedMax', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">trail length (px)</div>
				<input
					type="range"
					min="2"
					max="60"
					step="1"
					value={config.synapseTrailLength ?? 12}
					oninput={(e) => setNumber('synapseTrailLength', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'rain'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">streak color</div>
				<input
					type="color"
					value={config.rainColor ?? '#ffffff'}
					oninput={(e) => setString('rainColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.rainBackgroundColor ?? '#0d1117'}
					oninput={(e) => setString('rainBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">
					intensity (also drives speed + spawn rate)
				</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.rainIntensity ?? 0.5}
					oninput={(e) => setNumber('rainIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">size</div>
				<input
					type="range"
					min="0.2"
					max="3"
					step="0.05"
					value={config.rainSize ?? 1}
					oninput={(e) => setNumber('rainSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">max drops</div>
				<input
					type="range"
					min="10"
					max="500"
					step="10"
					value={config.rainMaxDrops ?? 130}
					oninput={(e) => setNumber('rainMaxDrops', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">spawn chance / frame</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.rainSpawnChance ?? 0.6}
					oninput={(e) => setNumber('rainSpawnChance', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'constellations'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">star color</div>
				<input
					type="color"
					value={config.constellationsColor ?? '#64d2ff'}
					oninput={(e) => setString('constellationsColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.constellationsBackgroundColor ?? '#0b1a2c'}
					oninput={(e) =>
						setString('constellationsBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.constellationsIntensity ?? 1}
					oninput={(e) => setNumber('constellationsIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">star count (pair cost is quadratic)</div>
				<input
					type="range"
					min="5"
					max="200"
					step="5"
					value={config.constellationsStarCount ?? 50}
					oninput={(e) => setNumber('constellationsStarCount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">connect distance (px)</div>
				<input
					type="range"
					min="20"
					max="400"
					step="5"
					value={config.constellationsConnectDistance ?? 120}
					oninput={(e) =>
						setNumber('constellationsConnectDistance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">drift speed</div>
				<input
					type="range"
					min="0"
					max="2"
					step="0.05"
					value={config.constellationsDriftSpeed ?? 0.15}
					oninput={(e) => setNumber('constellationsDriftSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">twinkle speed</div>
				<input
					type="range"
					min="0"
					max="0.1"
					step="0.002"
					value={config.constellationsTwinkleSpeed ?? 0.01}
					oninput={(e) => setNumber('constellationsTwinkleSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'perlin-flow'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">particle color</div>
				<input
					type="color"
					value={config.perlinFlowColor ?? '#00ff41'}
					oninput={(e) => setString('perlinFlowColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color (also the trail fade)</div>
				<input
					type="color"
					value={config.perlinFlowBackgroundColor ?? '#000000'}
					oninput={(e) => setString('perlinFlowBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.perlinFlowIntensity ?? 0.8}
					oninput={(e) => setNumber('perlinFlowIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">particle count</div>
				<input
					type="range"
					min="20"
					max="1000"
					step="10"
					value={config.perlinFlowParticleCount ?? 200}
					oninput={(e) => setNumber('perlinFlowParticleCount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">fade alpha (lower = longer trails)</div>
				<input
					type="range"
					min="0.005"
					max="0.3"
					step="0.005"
					value={config.perlinFlowFadeAlpha ?? 0.02}
					oninput={(e) => setNumber('perlinFlowFadeAlpha', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">noise scale</div>
				<input
					type="range"
					min="0.0005"
					max="0.02"
					step="0.0005"
					value={config.perlinFlowNoiseScale ?? 0.004}
					oninput={(e) => setNumber('perlinFlowNoiseScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">time scale</div>
				<input
					type="range"
					min="0"
					max="0.01"
					step="0.0002"
					value={config.perlinFlowTimeScale ?? 0.0008}
					oninput={(e) => setNumber('perlinFlowTimeScale', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">speed</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.1"
					value={config.perlinFlowSpeed ?? 1}
					oninput={(e) => setNumber('perlinFlowSpeed', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">dot radius (px)</div>
				<input
					type="range"
					min="0.5"
					max="5"
					step="0.5"
					value={config.perlinFlowDotRadius ?? 1}
					oninput={(e) => setNumber('perlinFlowDotRadius', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">life decay / frame</div>
				<input
					type="range"
					min="0.0002"
					max="0.02"
					step="0.0002"
					value={config.perlinFlowLifeDecay ?? 0.001}
					oninput={(e) => setNumber('perlinFlowLifeDecay', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'petals'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">petal color</div>
				<input
					type="color"
					value={config.petalsColor ?? '#f5a0c0'}
					oninput={(e) => setString('petalsColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.petalsBackgroundColor ?? '#2b1b2e'}
					oninput={(e) => setString('petalsBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.petalsIntensity ?? 1}
					oninput={(e) => setNumber('petalsIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">size</div>
				<input
					type="range"
					min="0.2"
					max="3"
					step="0.05"
					value={config.petalsSize ?? 1}
					oninput={(e) => setNumber('petalsSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">count</div>
				<input
					type="range"
					min="5"
					max="200"
					step="5"
					value={config.petalsCount ?? 30}
					oninput={(e) => setNumber('petalsCount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">fall speed</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.1"
					value={config.petalsFallSpeed ?? 1}
					oninput={(e) => setNumber('petalsFallSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'sparkles'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">sparkle color</div>
				<input
					type="color"
					value={config.sparklesColor ?? '#ff8cb8'}
					oninput={(e) => setString('sparklesColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.sparklesBackgroundColor ?? '#fff0f5'}
					oninput={(e) => setString('sparklesBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.sparklesIntensity ?? 1}
					oninput={(e) => setNumber('sparklesIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">size</div>
				<input
					type="range"
					min="0.2"
					max="3"
					step="0.05"
					value={config.sparklesSize ?? 1}
					oninput={(e) => setNumber('sparklesSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">count</div>
				<input
					type="range"
					min="5"
					max="250"
					step="5"
					value={config.sparklesCount ?? 35}
					oninput={(e) => setNumber('sparklesCount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">twinkle speed</div>
				<input
					type="range"
					min="0.1"
					max="5"
					step="0.1"
					value={config.sparklesTwinkleSpeed ?? 1}
					oninput={(e) => setNumber('sparklesTwinkleSpeed', e.currentTarget.value)}
				/>
			</div>
		{:else if renderer === 'embers'}
			<div class="border-foreground/10 bg-foreground/5 space-y-3 rounded-2xl border p-4">
				<div class="text-foreground/60 text-xs">ember color</div>
				<input
					type="color"
					value={config.embersColor ?? '#e94560'}
					oninput={(e) => setString('embersColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">background color</div>
				<input
					type="color"
					value={config.embersBackgroundColor ?? '#1a1a2e'}
					oninput={(e) => setString('embersBackgroundColor', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">intensity</div>
				<input
					type="range"
					min="0"
					max="1"
					step="0.05"
					value={config.embersIntensity ?? 1}
					oninput={(e) => setNumber('embersIntensity', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">size</div>
				<input
					type="range"
					min="0.2"
					max="3"
					step="0.05"
					value={config.embersSize ?? 1}
					oninput={(e) => setNumber('embersSize', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">count</div>
				<input
					type="range"
					min="10"
					max="300"
					step="5"
					value={config.embersCount ?? 60}
					oninput={(e) => setNumber('embersCount', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">fade alpha (lower = longer trails)</div>
				<input
					type="range"
					min="0.02"
					max="0.6"
					step="0.01"
					value={config.embersFadeAlpha ?? 0.18}
					oninput={(e) => setNumber('embersFadeAlpha', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">spark chance / frame</div>
				<input
					type="range"
					min="0"
					max="0.05"
					step="0.001"
					value={config.embersSparkChance ?? 0.003}
					oninput={(e) => setNumber('embersSparkChance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">burst chance / frame</div>
				<input
					type="range"
					min="0"
					max="0.2"
					step="0.005"
					value={config.embersBurstChance ?? 0.015}
					oninput={(e) => setNumber('embersBurstChance', e.currentTarget.value)}
				/>
				<div class="text-foreground/60 text-xs">burst size</div>
				<input
					type="range"
					min="1"
					max="30"
					step="1"
					value={config.embersBurstSize ?? 5}
					oninput={(e) => setNumber('embersBurstSize', e.currentTarget.value)}
				/>
			</div>
		{/if}

		<div class="border-foreground/10 bg-foreground/5 rounded-2xl border p-4">
			<div class="text-foreground/60 mb-2 text-xs">backgroundDefaults.ts snippet</div>
			<pre
				class="border-foreground/10 text-foreground/80 max-h-96 overflow-auto rounded-lg border bg-black/35 p-3 text-xs">{configSnippet}</pre>
		</div>
	</div>
</div>
