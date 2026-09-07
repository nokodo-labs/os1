<script lang="ts">
	import { device } from '$lib/stores/device.svelte'
	import { untrack } from 'svelte'
	import { BACKGROUND_DEFAULTS, BACKGROUND_RENDERER } from './backgroundDefaults'
	import DitherBackground from './css/DitherBackground.svelte'
	import DotsBackground from './css/DotsBackground.svelte'
	import OrbGlowBackground from './css/OrbGlowBackground.svelte'
	import StaticBackground from './StaticBackground.svelte'
	import AsciiOrbBackground from './canvas/AsciiOrbBackground.svelte'
	import Clouds2Background from './webgl/Clouds2Background.svelte'
	import CloudsBackground from './webgl/CloudsBackground.svelte'
	import ConstellationsBackground from './canvas/ConstellationsBackground.svelte'
	import DarkVeilBackground from './webgl/DarkVeilBackground.svelte'
	import EmbersBackground from './canvas/EmbersBackground.svelte'
	import FogBackground from './webgl/FogBackground.svelte'
	import GalaxyBackgroundWebGL from './webgl/GalaxyBackgroundWebGL.svelte'
	import GrainientBackground from './webgl/GrainientBackground.svelte'
	import IridescenceBackground from './webgl/IridescenceBackground.svelte'
	import LensGrainBackground from './webgl/LensGrainBackground.svelte'
	import LightBendsBackground from './webgl/LightBendsBackground.svelte'
	import LightRaysBackground from './webgl/LightRaysBackground.svelte'
	import PerlinFlowBackground from './canvas/PerlinFlowBackground.svelte'
	import PetalsBackground from './canvas/PetalsBackground.svelte'
	import RainBackground from './canvas/RainBackground.svelte'
	import SilkBackground from './webgl/SilkBackground.svelte'
	import SparklesBackground from './canvas/SparklesBackground.svelte'
	import SynapseBackground from './canvas/SynapseBackground.svelte'

	// every wallpaper that ships as a light/dark pair lists both siblings here:
	// they are independent, separately selectable wallpapers sharing one renderer.
	export type BackgroundType =
		| 'galaxy'
		| 'galaxy-light'
		| 'darkveil'
		| 'darkveil-light'
		| 'lightbends'
		| 'lightbends-light'
		| 'lightrays'
		| 'lightrays-light'
		| 'silk'
		| 'silk-light'
		| 'fog'
		| 'fog-light'
		| 'clouds'
		| 'clouds-dark'
		| 'clouds2'
		| 'clouds2-dark'
		| 'grainient'
		| 'grainient-dark'
		| 'iridescence'
		| 'iridescence-dark'
		| 'asciiorb'
		| 'asciiorb-light'
		| 'lensgrain'
		| 'lensgrain-light'
		| 'dither'
		| 'dither-light'
		| 'orbglow'
		| 'orbglow-light'
		| 'dots'
		| 'dots-dark'
		| 'synapse'
		| 'synapse-light'
		| 'rain'
		| 'rain-light'
		| 'constellations'
		| 'constellations-light'
		| 'perlin-flow'
		| 'perlin-flow-light'
		| 'petals'
		| 'petals-light'
		| 'sparkles'
		| 'sparkles-dark'
		| 'embers'
		| 'embers-light'
		| 'static'
		| 'none'

	export interface BackgroundConfig {
		// Static background options
		color?: string
		image?: string

		// LightBends options
		lightBendsColors?: string[]
		lightBendsSpeed?: number
		lightBendsWarp?: number
		lightBendsRotation?: number
		lightBendsAutoRotate?: number
		lightBendsScale?: number
		lightBendsFrequency?: number
		lightBendsMouseInfluence?: number
		lightBendsParallax?: number
		lightBendsNoise?: number

		// LightRays options
		raysOrigin?:
			| 'top-center'
			| 'top-left'
			| 'top-right'
			| 'right'
			| 'left'
			| 'bottom-center'
			| 'bottom-right'
			| 'bottom-left'
		raysColor?: string
		raysBackgroundColor?: string
		raysSpeed?: number
		raysLightSpread?: number
		raysRayLength?: number
		raysPulsating?: boolean
		raysFadeDistance?: number
		raysSaturation?: number
		raysFollowMouse?: boolean
		raysMouseInfluence?: number
		raysNoiseAmount?: number
		raysDistortion?: number

		// Silk options
		silkColor?: string
		silkBackgroundColor?: string
		silkSpeed?: number

		// DarkVeil options
		darkveilHueShift?: number
		darkveilNoiseIntensity?: number
		darkveilScanlineIntensity?: number
		darkveilSpeed?: number
		darkveilScanlineFrequency?: number
		darkveilWarpAmount?: number
		darkveilResolutionScale?: number
		darkveilTintColor?: string
		darkveilBackgroundColor?: string

		// Galaxy options
		galaxyFocalX?: number
		galaxyFocalY?: number
		galaxyRotationX?: number
		galaxyRotationY?: number
		galaxyStarSpeed?: number
		galaxyDensity?: number
		galaxySpeed?: number
		galaxyGlowIntensity?: number
		galaxyTwinkleIntensity?: number
		galaxyRotationSpeed?: number
		galaxyBackgroundColor?: string
		galaxyStarColor?: string

		// Fog options
		fogHighlightColor?: number
		fogMidtoneColor?: number
		fogLowlightColor?: number
		fogBaseColor?: number
		fogBlurFactor?: number
		fogSpeed?: number
		fogZoom?: number
		fogMouseControls?: boolean
		fogTouchControls?: boolean
		fogGyroControls?: boolean
		fogMinHeight?: number
		fogMinWidth?: number

		// Clouds options
		cloudsSkyColor?: number
		cloudsCloudColor?: number
		cloudsCloudShadowColor?: number
		cloudsSunColor?: number
		cloudsSunGlareColor?: number
		cloudsSunlightColor?: number
		cloudsSpeed?: number
		cloudsMouseControls?: boolean
		cloudsTouchControls?: boolean
		cloudsGyroControls?: boolean
		cloudsMinHeight?: number
		cloudsMinWidth?: number

		// Clouds2 options
		clouds2Scale?: number
		clouds2Speed?: number
		clouds2TexturePath?: string | null
		clouds2SkyColor?: number
		clouds2CloudColor?: number
		clouds2LightColor?: number
		clouds2BackgroundColor?: number
		clouds2MouseControls?: boolean
		clouds2TouchControls?: boolean
		clouds2GyroControls?: boolean
		clouds2MinHeight?: number
		clouds2MinWidth?: number

		// Grainient options
		grainientTimeSpeed?: number
		grainientColorBalance?: number
		grainientWarpStrength?: number
		grainientWarpFrequency?: number
		grainientWarpSpeed?: number
		grainientWarpAmplitude?: number
		grainientBlendAngle?: number
		grainientBlendSoftness?: number
		grainientRotationAmount?: number
		grainientNoiseScale?: number
		grainientGrainAmount?: number
		grainientGrainScale?: number
		grainientGrainAnimated?: boolean
		grainientContrast?: number
		grainientGamma?: number
		grainientSaturation?: number
		grainientCenterX?: number
		grainientCenterY?: number
		grainientZoom?: number
		grainientColor1?: string
		grainientColor2?: string
		grainientColor3?: string

		// Iridescence options
		iridescenceColor?: [number, number, number]
		iridescenceSpeed?: number
		iridescenceAmplitude?: number
		iridescenceMouseReact?: boolean

		// AsciiOrb options
		asciiOrbColor?: string
		asciiOrbBackgroundColor?: string
		asciiOrbFontSize?: number
		asciiOrbRadius?: number
		asciiOrbZoom?: number
		asciiOrbSpin?: number
		asciiOrbTilt?: number
		asciiOrbWire?: number
		asciiOrbLatitudes?: number
		asciiOrbLongitudes?: number
		asciiOrbShape?: 'sphere' | 'cube'
		asciiOrbCubeScale?: number
		asciiOrbMorphDuration?: number
		asciiOrbBuildDuration?: number

		// LensGrain options
		lensGrainColor?: string
		lensGrainBackgroundColor?: string
		lensGrainDensity?: number
		lensGrainOpacity?: number
		lensGrainSize?: number
		lensGrainAnimated?: boolean
		lensGrainVignetteColor?: string
		lensGrainVignetteOpacity?: number

		// Dither options
		ditherColor?: string
		ditherAccentColor?: string
		ditherGlowStrength?: number
		ditherGlowSpread?: number
		ditherDotStrength?: number
		ditherDotSize?: number

		// OrbGlow options
		orbGlowColor?: string
		orbGlowHaloColor?: string
		orbGlowBackgroundColor?: string
		orbGlowCoreOpacity?: number
		orbGlowHaloOpacity?: number
		orbGlowRadius?: number
		orbGlowFollowPointer?: boolean
		orbGlowDrift?: number
		orbGlowEasing?: number

		// Dots options (odysseus)
		dotsColor?: string
		dotsBackgroundColor?: string
		dotsIntensity?: number
		dotsSpacing?: number
		dotsStrength?: number
		dotsDotSize?: number

		// Synapse options (odysseus)
		synapseColor?: string
		synapseBackgroundColor?: string
		synapseIntensity?: number
		synapseGrid?: number
		synapseGridStrength?: number
		synapseMaxPulses?: number
		synapseSpawnChance?: number
		synapseSpeedMin?: number
		synapseSpeedMax?: number
		synapseTrailLength?: number

		// Rain options (odysseus)
		rainColor?: string
		rainBackgroundColor?: string
		rainIntensity?: number
		rainSize?: number
		rainMaxDrops?: number
		rainSpawnChance?: number

		// Constellations options (odysseus)
		constellationsColor?: string
		constellationsBackgroundColor?: string
		constellationsIntensity?: number
		constellationsStarCount?: number
		constellationsConnectDistance?: number
		constellationsDriftSpeed?: number
		constellationsTwinkleSpeed?: number

		// PerlinFlow options (odysseus)
		perlinFlowColor?: string
		perlinFlowBackgroundColor?: string
		perlinFlowIntensity?: number
		perlinFlowParticleCount?: number
		perlinFlowFadeAlpha?: number
		perlinFlowNoiseScale?: number
		perlinFlowTimeScale?: number
		perlinFlowSpeed?: number
		perlinFlowDotRadius?: number
		perlinFlowLifeDecay?: number

		// Petals options (odysseus)
		petalsColor?: string
		petalsBackgroundColor?: string
		petalsIntensity?: number
		petalsSize?: number
		petalsCount?: number
		petalsFallSpeed?: number

		// Sparkles options (odysseus)
		sparklesColor?: string
		sparklesBackgroundColor?: string
		sparklesIntensity?: number
		sparklesSize?: number
		sparklesCount?: number
		sparklesTwinkleSpeed?: number

		// Embers options (odysseus)
		embersColor?: string
		embersBackgroundColor?: string
		embersIntensity?: number
		embersSize?: number
		embersCount?: number
		embersFadeAlpha?: number
		embersSparkChance?: number
		embersBurstChance?: number
		embersBurstSize?: number
	}

	interface Props {
		type: BackgroundType
		config?: BackgroundConfig
		onReady?: (bg: BackgroundType) => void
	}

	let { type = 'galaxy', config = {}, onReady }: Props = $props()

	// readiness is keyed on the currently painted background so onReady fires
	// once per settled background (re-armed across transitions), letting callers
	// gate on the FINAL background rather than the first one that ever rendered.
	let readyBg = $state<BackgroundType | null>(null)
	function signalReady() {
		if (readyBg === currentBg) return
		readyBg = currentBg
		onReady?.(currentBg)
	}

	// Transition state for smooth swapping
	let currentBg = $state<BackgroundType>('galaxy')
	currentBg = untrack(() => type)
	let previousBg = $state<BackgroundType | null>(null)
	let isTransitioning = $state(false)

	// both siblings of a light/dark pair paint through the same component, so the
	// template branches on the renderer while the config stays per wallpaper
	const currentRenderer = $derived(BACKGROUND_RENDERER[currentBg])
	const previousRenderer = $derived(previousBg === null ? null : BACKGROUND_RENDERER[previousBg])

	// merge centralized defaults with the caller-supplied override so every
	// prop always has a sensible value without inline || fallbacks in the template
	const resolvedConfig = $derived<BackgroundConfig>({
		...BACKGROUND_DEFAULTS[currentBg],
		...config,
	})

	$effect(() => {
		if (type !== currentBg && !isTransitioning) {
			isTransitioning = true
			previousBg = currentBg

			// Use rAF to batch the state update with the next paint,
			// then a single timeout for the cross-fade duration.
			requestAnimationFrame(() => {
				currentBg = type
				setTimeout(() => {
					previousBg = null
					isTransitioning = false
				}, 300) // match CSS transition duration
			})
		}
	})

	$effect(() => {
		if (currentRenderer === 'static' || currentRenderer === 'none') {
			signalReady()
		}
	})

	// the wallpaper holds ONE size across virtual-keyboard open/close: android
	// shrinks the layout viewport for the keyboard now
	// (`interactive-widget=resizes-content`), and a fixed layer that follows it
	// reflows on every toggle - the canvas renderers re-seed their fields on each
	// resize. the ratcheted height still follows rotation and window resizes, and
	// is 0 until the device store syncs, where the `inset-0` stretch takes over.
	const layerHeight = $derived(
		device.stableViewportHeight > 0 ? `${device.stableViewportHeight}px` : null
	)
</script>

<!-- wallpaper layer only. the app shell is a sibling (see routes/+layout.svelte) so it
     never lives inside this stacking context. anchored top and clipped: it paints edge
     to edge behind a viewport the keyboard has shrunk. -->
<div class="fixed inset-0 -z-10 overflow-hidden" style:height={layerHeight}>
	{#if previousBg && isTransitioning}
		<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
			{#if previousRenderer === 'galaxy'}
				<GalaxyBackgroundWebGL
					focalX={resolvedConfig.galaxyFocalX}
					focalY={resolvedConfig.galaxyFocalY}
					rotationX={resolvedConfig.galaxyRotationX}
					rotationY={resolvedConfig.galaxyRotationY}
					starSpeed={resolvedConfig.galaxyStarSpeed}
					density={resolvedConfig.galaxyDensity}
					speed={resolvedConfig.galaxySpeed}
					glowIntensity={resolvedConfig.galaxyGlowIntensity}
					twinkleIntensity={resolvedConfig.galaxyTwinkleIntensity}
					rotationSpeed={resolvedConfig.galaxyRotationSpeed}
					backgroundColor={resolvedConfig.galaxyBackgroundColor}
					starColor={resolvedConfig.galaxyStarColor}
				/>
			{:else if previousRenderer === 'darkveil'}
				<DarkVeilBackground
					hueShift={resolvedConfig.darkveilHueShift}
					noiseIntensity={resolvedConfig.darkveilNoiseIntensity}
					scanlineIntensity={resolvedConfig.darkveilScanlineIntensity}
					speed={resolvedConfig.darkveilSpeed}
					scanlineFrequency={resolvedConfig.darkveilScanlineFrequency}
					warpAmount={resolvedConfig.darkveilWarpAmount}
					resolutionScale={resolvedConfig.darkveilResolutionScale}
					tintColor={resolvedConfig.darkveilTintColor}
					backgroundColor={resolvedConfig.darkveilBackgroundColor}
				/>
			{:else if previousRenderer === 'lightbends'}
				<LightBendsBackground
					colors={resolvedConfig.lightBendsColors}
					speed={resolvedConfig.lightBendsSpeed}
					warpStrength={resolvedConfig.lightBendsWarp}
					rotation={resolvedConfig.lightBendsRotation}
					autoRotate={resolvedConfig.lightBendsAutoRotate}
					scale={resolvedConfig.lightBendsScale}
					frequency={resolvedConfig.lightBendsFrequency}
					mouseInfluence={resolvedConfig.lightBendsMouseInfluence}
					parallax={resolvedConfig.lightBendsParallax}
					noise={resolvedConfig.lightBendsNoise}
				/>
			{:else if previousRenderer === 'lightrays'}
				<LightRaysBackground
					raysOrigin={resolvedConfig.raysOrigin}
					raysColor={resolvedConfig.raysColor}
					backgroundColor={resolvedConfig.raysBackgroundColor}
					raysSpeed={resolvedConfig.raysSpeed}
					lightSpread={resolvedConfig.raysLightSpread}
					rayLength={resolvedConfig.raysRayLength}
					pulsating={resolvedConfig.raysPulsating}
					fadeDistance={resolvedConfig.raysFadeDistance}
					saturation={resolvedConfig.raysSaturation}
					followMouse={resolvedConfig.raysFollowMouse}
					mouseInfluence={resolvedConfig.raysMouseInfluence}
					noiseAmount={resolvedConfig.raysNoiseAmount}
					distortion={resolvedConfig.raysDistortion}
				/>
			{:else if previousRenderer === 'silk'}
				<SilkBackground
					color={resolvedConfig.silkColor}
					backgroundColor={resolvedConfig.silkBackgroundColor}
					speed={resolvedConfig.silkSpeed}
				/>
			{:else if previousRenderer === 'fog'}
				<FogBackground
					mouseControls={resolvedConfig.fogMouseControls}
					touchControls={resolvedConfig.fogTouchControls}
					gyroControls={resolvedConfig.fogGyroControls}
					minHeight={resolvedConfig.fogMinHeight}
					minWidth={resolvedConfig.fogMinWidth}
					highlightColor={resolvedConfig.fogHighlightColor}
					midtoneColor={resolvedConfig.fogMidtoneColor}
					lowlightColor={resolvedConfig.fogLowlightColor}
					baseColor={resolvedConfig.fogBaseColor}
					blurFactor={resolvedConfig.fogBlurFactor}
					speed={resolvedConfig.fogSpeed}
					zoom={resolvedConfig.fogZoom}
				/>
			{:else if previousRenderer === 'clouds'}
				<CloudsBackground
					mouseControls={resolvedConfig.cloudsMouseControls}
					touchControls={resolvedConfig.cloudsTouchControls}
					gyroControls={resolvedConfig.cloudsGyroControls}
					minHeight={resolvedConfig.cloudsMinHeight}
					minWidth={resolvedConfig.cloudsMinWidth}
					skyColor={resolvedConfig.cloudsSkyColor}
					cloudColor={resolvedConfig.cloudsCloudColor}
					cloudShadowColor={resolvedConfig.cloudsCloudShadowColor}
					sunColor={resolvedConfig.cloudsSunColor}
					sunGlareColor={resolvedConfig.cloudsSunGlareColor}
					sunlightColor={resolvedConfig.cloudsSunlightColor}
					speed={resolvedConfig.cloudsSpeed}
				/>
			{:else if previousRenderer === 'clouds2'}
				<Clouds2Background
					mouseControls={resolvedConfig.clouds2MouseControls}
					touchControls={resolvedConfig.clouds2TouchControls}
					gyroControls={resolvedConfig.clouds2GyroControls}
					minHeight={resolvedConfig.clouds2MinHeight}
					minWidth={resolvedConfig.clouds2MinWidth}
					scale={resolvedConfig.clouds2Scale}
					speed={resolvedConfig.clouds2Speed}
					texturePath={resolvedConfig.clouds2TexturePath}
					skyColor={resolvedConfig.clouds2SkyColor}
					cloudColor={resolvedConfig.clouds2CloudColor}
					lightColor={resolvedConfig.clouds2LightColor}
					backgroundColor={resolvedConfig.clouds2BackgroundColor}
				/>
			{:else if previousRenderer === 'grainient'}
				<GrainientBackground
					timeSpeed={resolvedConfig.grainientTimeSpeed}
					colorBalance={resolvedConfig.grainientColorBalance}
					warpStrength={resolvedConfig.grainientWarpStrength}
					warpFrequency={resolvedConfig.grainientWarpFrequency}
					warpSpeed={resolvedConfig.grainientWarpSpeed}
					warpAmplitude={resolvedConfig.grainientWarpAmplitude}
					blendAngle={resolvedConfig.grainientBlendAngle}
					blendSoftness={resolvedConfig.grainientBlendSoftness}
					rotationAmount={resolvedConfig.grainientRotationAmount}
					noiseScale={resolvedConfig.grainientNoiseScale}
					grainAmount={resolvedConfig.grainientGrainAmount}
					grainScale={resolvedConfig.grainientGrainScale}
					grainAnimated={resolvedConfig.grainientGrainAnimated}
					contrast={resolvedConfig.grainientContrast}
					gamma={resolvedConfig.grainientGamma}
					saturation={resolvedConfig.grainientSaturation}
					centerX={resolvedConfig.grainientCenterX}
					centerY={resolvedConfig.grainientCenterY}
					zoom={resolvedConfig.grainientZoom}
					color1={resolvedConfig.grainientColor1}
					color2={resolvedConfig.grainientColor2}
					color3={resolvedConfig.grainientColor3}
				/>
			{:else if previousRenderer === 'iridescence'}
				<IridescenceBackground
					color={resolvedConfig.iridescenceColor}
					speed={resolvedConfig.iridescenceSpeed}
					amplitude={resolvedConfig.iridescenceAmplitude}
					mouseReact={resolvedConfig.iridescenceMouseReact}
				/>
			{:else if previousRenderer === 'asciiorb'}
				<AsciiOrbBackground
					color={resolvedConfig.asciiOrbColor}
					backgroundColor={resolvedConfig.asciiOrbBackgroundColor}
					fontSize={resolvedConfig.asciiOrbFontSize}
					radius={resolvedConfig.asciiOrbRadius}
					zoom={resolvedConfig.asciiOrbZoom}
					spin={resolvedConfig.asciiOrbSpin}
					tilt={resolvedConfig.asciiOrbTilt}
					wire={resolvedConfig.asciiOrbWire}
					latitudes={resolvedConfig.asciiOrbLatitudes}
					longitudes={resolvedConfig.asciiOrbLongitudes}
					shape={resolvedConfig.asciiOrbShape}
					cubeScale={resolvedConfig.asciiOrbCubeScale}
					morphDuration={resolvedConfig.asciiOrbMorphDuration}
					buildDuration={resolvedConfig.asciiOrbBuildDuration}
				/>
			{:else if previousRenderer === 'lensgrain'}
				<LensGrainBackground
					color={resolvedConfig.lensGrainColor}
					backgroundColor={resolvedConfig.lensGrainBackgroundColor}
					density={resolvedConfig.lensGrainDensity}
					opacity={resolvedConfig.lensGrainOpacity}
					size={resolvedConfig.lensGrainSize}
					animated={resolvedConfig.lensGrainAnimated}
					vignetteColor={resolvedConfig.lensGrainVignetteColor}
					vignetteOpacity={resolvedConfig.lensGrainVignetteOpacity}
				/>
			{:else if previousRenderer === 'dither'}
				<DitherBackground
					color={resolvedConfig.ditherColor}
					accentColor={resolvedConfig.ditherAccentColor}
					glowStrength={resolvedConfig.ditherGlowStrength}
					glowSpread={resolvedConfig.ditherGlowSpread}
					dotStrength={resolvedConfig.ditherDotStrength}
					dotSize={resolvedConfig.ditherDotSize}
				/>
			{:else if previousRenderer === 'orbglow'}
				<OrbGlowBackground
					color={resolvedConfig.orbGlowColor}
					haloColor={resolvedConfig.orbGlowHaloColor}
					backgroundColor={resolvedConfig.orbGlowBackgroundColor}
					coreOpacity={resolvedConfig.orbGlowCoreOpacity}
					haloOpacity={resolvedConfig.orbGlowHaloOpacity}
					radius={resolvedConfig.orbGlowRadius}
					followPointer={resolvedConfig.orbGlowFollowPointer}
					drift={resolvedConfig.orbGlowDrift}
					easing={resolvedConfig.orbGlowEasing}
				/>
			{:else if previousRenderer === 'dots'}
				<DotsBackground
					color={resolvedConfig.dotsColor}
					backgroundColor={resolvedConfig.dotsBackgroundColor}
					intensity={resolvedConfig.dotsIntensity}
					spacing={resolvedConfig.dotsSpacing}
					strength={resolvedConfig.dotsStrength}
					dotSize={resolvedConfig.dotsDotSize}
				/>
			{:else if previousRenderer === 'synapse'}
				<SynapseBackground
					color={resolvedConfig.synapseColor}
					backgroundColor={resolvedConfig.synapseBackgroundColor}
					intensity={resolvedConfig.synapseIntensity}
					grid={resolvedConfig.synapseGrid}
					gridStrength={resolvedConfig.synapseGridStrength}
					maxPulses={resolvedConfig.synapseMaxPulses}
					spawnChance={resolvedConfig.synapseSpawnChance}
					speedMin={resolvedConfig.synapseSpeedMin}
					speedMax={resolvedConfig.synapseSpeedMax}
					trailLength={resolvedConfig.synapseTrailLength}
				/>
			{:else if previousRenderer === 'rain'}
				<RainBackground
					color={resolvedConfig.rainColor}
					backgroundColor={resolvedConfig.rainBackgroundColor}
					intensity={resolvedConfig.rainIntensity}
					size={resolvedConfig.rainSize}
					maxDrops={resolvedConfig.rainMaxDrops}
					spawnChance={resolvedConfig.rainSpawnChance}
				/>
			{:else if previousRenderer === 'constellations'}
				<ConstellationsBackground
					color={resolvedConfig.constellationsColor}
					backgroundColor={resolvedConfig.constellationsBackgroundColor}
					intensity={resolvedConfig.constellationsIntensity}
					starCount={resolvedConfig.constellationsStarCount}
					connectDistance={resolvedConfig.constellationsConnectDistance}
					driftSpeed={resolvedConfig.constellationsDriftSpeed}
					twinkleSpeed={resolvedConfig.constellationsTwinkleSpeed}
				/>
			{:else if previousRenderer === 'perlin-flow'}
				<PerlinFlowBackground
					color={resolvedConfig.perlinFlowColor}
					backgroundColor={resolvedConfig.perlinFlowBackgroundColor}
					intensity={resolvedConfig.perlinFlowIntensity}
					particleCount={resolvedConfig.perlinFlowParticleCount}
					fadeAlpha={resolvedConfig.perlinFlowFadeAlpha}
					noiseScale={resolvedConfig.perlinFlowNoiseScale}
					timeScale={resolvedConfig.perlinFlowTimeScale}
					speed={resolvedConfig.perlinFlowSpeed}
					dotRadius={resolvedConfig.perlinFlowDotRadius}
					lifeDecay={resolvedConfig.perlinFlowLifeDecay}
				/>
			{:else if previousRenderer === 'petals'}
				<PetalsBackground
					color={resolvedConfig.petalsColor}
					backgroundColor={resolvedConfig.petalsBackgroundColor}
					intensity={resolvedConfig.petalsIntensity}
					size={resolvedConfig.petalsSize}
					count={resolvedConfig.petalsCount}
					fallSpeed={resolvedConfig.petalsFallSpeed}
				/>
			{:else if previousRenderer === 'sparkles'}
				<SparklesBackground
					color={resolvedConfig.sparklesColor}
					backgroundColor={resolvedConfig.sparklesBackgroundColor}
					intensity={resolvedConfig.sparklesIntensity}
					size={resolvedConfig.sparklesSize}
					count={resolvedConfig.sparklesCount}
					twinkleSpeed={resolvedConfig.sparklesTwinkleSpeed}
				/>
			{:else if previousRenderer === 'embers'}
				<EmbersBackground
					color={resolvedConfig.embersColor}
					backgroundColor={resolvedConfig.embersBackgroundColor}
					intensity={resolvedConfig.embersIntensity}
					size={resolvedConfig.embersSize}
					count={resolvedConfig.embersCount}
					fadeAlpha={resolvedConfig.embersFadeAlpha}
					sparkChance={resolvedConfig.embersSparkChance}
					burstChance={resolvedConfig.embersBurstChance}
					burstSize={resolvedConfig.embersBurstSize}
				/>
			{:else if previousRenderer === 'static'}
				<StaticBackground color={resolvedConfig.color} image={resolvedConfig.image} />
			{/if}
		</div>
	{/if}

	<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
		{#if currentRenderer === 'galaxy'}
			<GalaxyBackgroundWebGL
				focalX={resolvedConfig.galaxyFocalX}
				focalY={resolvedConfig.galaxyFocalY}
				rotationX={resolvedConfig.galaxyRotationX}
				rotationY={resolvedConfig.galaxyRotationY}
				starSpeed={resolvedConfig.galaxyStarSpeed}
				density={resolvedConfig.galaxyDensity}
				speed={resolvedConfig.galaxySpeed}
				glowIntensity={resolvedConfig.galaxyGlowIntensity}
				twinkleIntensity={resolvedConfig.galaxyTwinkleIntensity}
				rotationSpeed={resolvedConfig.galaxyRotationSpeed}
				backgroundColor={resolvedConfig.galaxyBackgroundColor}
				starColor={resolvedConfig.galaxyStarColor}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'darkveil'}
			<DarkVeilBackground
				hueShift={resolvedConfig.darkveilHueShift}
				noiseIntensity={resolvedConfig.darkveilNoiseIntensity}
				scanlineIntensity={resolvedConfig.darkveilScanlineIntensity}
				speed={resolvedConfig.darkveilSpeed}
				scanlineFrequency={resolvedConfig.darkveilScanlineFrequency}
				warpAmount={resolvedConfig.darkveilWarpAmount}
				resolutionScale={resolvedConfig.darkveilResolutionScale}
				tintColor={resolvedConfig.darkveilTintColor}
				backgroundColor={resolvedConfig.darkveilBackgroundColor}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'lightbends'}
			<LightBendsBackground
				colors={resolvedConfig.lightBendsColors}
				speed={resolvedConfig.lightBendsSpeed}
				warpStrength={resolvedConfig.lightBendsWarp}
				rotation={resolvedConfig.lightBendsRotation}
				autoRotate={resolvedConfig.lightBendsAutoRotate}
				scale={resolvedConfig.lightBendsScale}
				frequency={resolvedConfig.lightBendsFrequency}
				mouseInfluence={resolvedConfig.lightBendsMouseInfluence}
				parallax={resolvedConfig.lightBendsParallax}
				noise={resolvedConfig.lightBendsNoise}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'lightrays'}
			<LightRaysBackground
				raysOrigin={resolvedConfig.raysOrigin}
				raysColor={resolvedConfig.raysColor}
				backgroundColor={resolvedConfig.raysBackgroundColor}
				raysSpeed={resolvedConfig.raysSpeed}
				lightSpread={resolvedConfig.raysLightSpread}
				rayLength={resolvedConfig.raysRayLength}
				pulsating={resolvedConfig.raysPulsating}
				fadeDistance={resolvedConfig.raysFadeDistance}
				saturation={resolvedConfig.raysSaturation}
				followMouse={resolvedConfig.raysFollowMouse}
				mouseInfluence={resolvedConfig.raysMouseInfluence}
				noiseAmount={resolvedConfig.raysNoiseAmount}
				distortion={resolvedConfig.raysDistortion}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'silk'}
			<SilkBackground
				color={resolvedConfig.silkColor}
				backgroundColor={resolvedConfig.silkBackgroundColor}
				speed={resolvedConfig.silkSpeed}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'fog'}
			<FogBackground
				mouseControls={resolvedConfig.fogMouseControls}
				touchControls={resolvedConfig.fogTouchControls}
				gyroControls={resolvedConfig.fogGyroControls}
				minHeight={resolvedConfig.fogMinHeight}
				minWidth={resolvedConfig.fogMinWidth}
				highlightColor={resolvedConfig.fogHighlightColor}
				midtoneColor={resolvedConfig.fogMidtoneColor}
				lowlightColor={resolvedConfig.fogLowlightColor}
				baseColor={resolvedConfig.fogBaseColor}
				blurFactor={resolvedConfig.fogBlurFactor}
				speed={resolvedConfig.fogSpeed}
				zoom={resolvedConfig.fogZoom}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'clouds'}
			<CloudsBackground
				mouseControls={resolvedConfig.cloudsMouseControls}
				touchControls={resolvedConfig.cloudsTouchControls}
				gyroControls={resolvedConfig.cloudsGyroControls}
				minHeight={resolvedConfig.cloudsMinHeight}
				minWidth={resolvedConfig.cloudsMinWidth}
				skyColor={resolvedConfig.cloudsSkyColor}
				cloudColor={resolvedConfig.cloudsCloudColor}
				cloudShadowColor={resolvedConfig.cloudsCloudShadowColor}
				sunColor={resolvedConfig.cloudsSunColor}
				sunGlareColor={resolvedConfig.cloudsSunGlareColor}
				sunlightColor={resolvedConfig.cloudsSunlightColor}
				speed={resolvedConfig.cloudsSpeed}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'clouds2'}
			<Clouds2Background
				mouseControls={resolvedConfig.clouds2MouseControls}
				touchControls={resolvedConfig.clouds2TouchControls}
				gyroControls={resolvedConfig.clouds2GyroControls}
				minHeight={resolvedConfig.clouds2MinHeight}
				minWidth={resolvedConfig.clouds2MinWidth}
				scale={resolvedConfig.clouds2Scale}
				speed={resolvedConfig.clouds2Speed}
				texturePath={resolvedConfig.clouds2TexturePath}
				skyColor={resolvedConfig.clouds2SkyColor}
				cloudColor={resolvedConfig.clouds2CloudColor}
				lightColor={resolvedConfig.clouds2LightColor}
				backgroundColor={resolvedConfig.clouds2BackgroundColor}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'grainient'}
			<GrainientBackground
				timeSpeed={resolvedConfig.grainientTimeSpeed}
				colorBalance={resolvedConfig.grainientColorBalance}
				warpStrength={resolvedConfig.grainientWarpStrength}
				warpFrequency={resolvedConfig.grainientWarpFrequency}
				warpSpeed={resolvedConfig.grainientWarpSpeed}
				warpAmplitude={resolvedConfig.grainientWarpAmplitude}
				blendAngle={resolvedConfig.grainientBlendAngle}
				blendSoftness={resolvedConfig.grainientBlendSoftness}
				rotationAmount={resolvedConfig.grainientRotationAmount}
				noiseScale={resolvedConfig.grainientNoiseScale}
				grainAmount={resolvedConfig.grainientGrainAmount}
				grainScale={resolvedConfig.grainientGrainScale}
				grainAnimated={resolvedConfig.grainientGrainAnimated}
				contrast={resolvedConfig.grainientContrast}
				gamma={resolvedConfig.grainientGamma}
				saturation={resolvedConfig.grainientSaturation}
				centerX={resolvedConfig.grainientCenterX}
				centerY={resolvedConfig.grainientCenterY}
				zoom={resolvedConfig.grainientZoom}
				color1={resolvedConfig.grainientColor1}
				color2={resolvedConfig.grainientColor2}
				color3={resolvedConfig.grainientColor3}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'iridescence'}
			<IridescenceBackground
				color={resolvedConfig.iridescenceColor}
				speed={resolvedConfig.iridescenceSpeed}
				amplitude={resolvedConfig.iridescenceAmplitude}
				mouseReact={resolvedConfig.iridescenceMouseReact}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'asciiorb'}
			<AsciiOrbBackground
				color={resolvedConfig.asciiOrbColor}
				backgroundColor={resolvedConfig.asciiOrbBackgroundColor}
				fontSize={resolvedConfig.asciiOrbFontSize}
				radius={resolvedConfig.asciiOrbRadius}
				zoom={resolvedConfig.asciiOrbZoom}
				spin={resolvedConfig.asciiOrbSpin}
				tilt={resolvedConfig.asciiOrbTilt}
				wire={resolvedConfig.asciiOrbWire}
				latitudes={resolvedConfig.asciiOrbLatitudes}
				longitudes={resolvedConfig.asciiOrbLongitudes}
				shape={resolvedConfig.asciiOrbShape}
				cubeScale={resolvedConfig.asciiOrbCubeScale}
				morphDuration={resolvedConfig.asciiOrbMorphDuration}
				buildDuration={resolvedConfig.asciiOrbBuildDuration}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'lensgrain'}
			<LensGrainBackground
				color={resolvedConfig.lensGrainColor}
				backgroundColor={resolvedConfig.lensGrainBackgroundColor}
				density={resolvedConfig.lensGrainDensity}
				opacity={resolvedConfig.lensGrainOpacity}
				size={resolvedConfig.lensGrainSize}
				animated={resolvedConfig.lensGrainAnimated}
				vignetteColor={resolvedConfig.lensGrainVignetteColor}
				vignetteOpacity={resolvedConfig.lensGrainVignetteOpacity}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'dither'}
			<DitherBackground
				color={resolvedConfig.ditherColor}
				accentColor={resolvedConfig.ditherAccentColor}
				glowStrength={resolvedConfig.ditherGlowStrength}
				glowSpread={resolvedConfig.ditherGlowSpread}
				dotStrength={resolvedConfig.ditherDotStrength}
				dotSize={resolvedConfig.ditherDotSize}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'orbglow'}
			<OrbGlowBackground
				color={resolvedConfig.orbGlowColor}
				haloColor={resolvedConfig.orbGlowHaloColor}
				backgroundColor={resolvedConfig.orbGlowBackgroundColor}
				coreOpacity={resolvedConfig.orbGlowCoreOpacity}
				haloOpacity={resolvedConfig.orbGlowHaloOpacity}
				radius={resolvedConfig.orbGlowRadius}
				followPointer={resolvedConfig.orbGlowFollowPointer}
				drift={resolvedConfig.orbGlowDrift}
				easing={resolvedConfig.orbGlowEasing}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'dots'}
			<DotsBackground
				color={resolvedConfig.dotsColor}
				backgroundColor={resolvedConfig.dotsBackgroundColor}
				intensity={resolvedConfig.dotsIntensity}
				spacing={resolvedConfig.dotsSpacing}
				strength={resolvedConfig.dotsStrength}
				dotSize={resolvedConfig.dotsDotSize}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'synapse'}
			<SynapseBackground
				color={resolvedConfig.synapseColor}
				backgroundColor={resolvedConfig.synapseBackgroundColor}
				intensity={resolvedConfig.synapseIntensity}
				grid={resolvedConfig.synapseGrid}
				gridStrength={resolvedConfig.synapseGridStrength}
				maxPulses={resolvedConfig.synapseMaxPulses}
				spawnChance={resolvedConfig.synapseSpawnChance}
				speedMin={resolvedConfig.synapseSpeedMin}
				speedMax={resolvedConfig.synapseSpeedMax}
				trailLength={resolvedConfig.synapseTrailLength}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'rain'}
			<RainBackground
				color={resolvedConfig.rainColor}
				backgroundColor={resolvedConfig.rainBackgroundColor}
				intensity={resolvedConfig.rainIntensity}
				size={resolvedConfig.rainSize}
				maxDrops={resolvedConfig.rainMaxDrops}
				spawnChance={resolvedConfig.rainSpawnChance}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'constellations'}
			<ConstellationsBackground
				color={resolvedConfig.constellationsColor}
				backgroundColor={resolvedConfig.constellationsBackgroundColor}
				intensity={resolvedConfig.constellationsIntensity}
				starCount={resolvedConfig.constellationsStarCount}
				connectDistance={resolvedConfig.constellationsConnectDistance}
				driftSpeed={resolvedConfig.constellationsDriftSpeed}
				twinkleSpeed={resolvedConfig.constellationsTwinkleSpeed}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'perlin-flow'}
			<PerlinFlowBackground
				color={resolvedConfig.perlinFlowColor}
				backgroundColor={resolvedConfig.perlinFlowBackgroundColor}
				intensity={resolvedConfig.perlinFlowIntensity}
				particleCount={resolvedConfig.perlinFlowParticleCount}
				fadeAlpha={resolvedConfig.perlinFlowFadeAlpha}
				noiseScale={resolvedConfig.perlinFlowNoiseScale}
				timeScale={resolvedConfig.perlinFlowTimeScale}
				speed={resolvedConfig.perlinFlowSpeed}
				dotRadius={resolvedConfig.perlinFlowDotRadius}
				lifeDecay={resolvedConfig.perlinFlowLifeDecay}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'petals'}
			<PetalsBackground
				color={resolvedConfig.petalsColor}
				backgroundColor={resolvedConfig.petalsBackgroundColor}
				intensity={resolvedConfig.petalsIntensity}
				size={resolvedConfig.petalsSize}
				count={resolvedConfig.petalsCount}
				fallSpeed={resolvedConfig.petalsFallSpeed}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'sparkles'}
			<SparklesBackground
				color={resolvedConfig.sparklesColor}
				backgroundColor={resolvedConfig.sparklesBackgroundColor}
				intensity={resolvedConfig.sparklesIntensity}
				size={resolvedConfig.sparklesSize}
				count={resolvedConfig.sparklesCount}
				twinkleSpeed={resolvedConfig.sparklesTwinkleSpeed}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'embers'}
			<EmbersBackground
				color={resolvedConfig.embersColor}
				backgroundColor={resolvedConfig.embersBackgroundColor}
				intensity={resolvedConfig.embersIntensity}
				size={resolvedConfig.embersSize}
				count={resolvedConfig.embersCount}
				fadeAlpha={resolvedConfig.embersFadeAlpha}
				sparkChance={resolvedConfig.embersSparkChance}
				burstChance={resolvedConfig.embersBurstChance}
				burstSize={resolvedConfig.embersBurstSize}
				onReady={signalReady}
			/>
		{:else if currentRenderer === 'static'}
			<StaticBackground color={resolvedConfig.color} image={resolvedConfig.image} />
		{/if}
	</div>
</div>
