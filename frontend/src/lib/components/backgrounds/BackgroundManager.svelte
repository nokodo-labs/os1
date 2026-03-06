<script lang="ts">
	import { untrack, type Snippet } from 'svelte'
	import { BACKGROUND_DEFAULTS } from './backgroundDefaults'
	import StaticBackground from './StaticBackground.svelte'
	import Clouds2Background from './webgl/Clouds2Background.svelte'
	import CloudsBackground from './webgl/CloudsBackground.svelte'
	import DarkVeilBackground from './webgl/DarkVeilBackground.svelte'
	import FogBackground from './webgl/FogBackground.svelte'
	import GalaxyBackgroundWebGL from './webgl/GalaxyBackgroundWebGL.svelte'
	import GrainientBackground from './webgl/GrainientBackground.svelte'
	import IridescenceBackground from './webgl/IridescenceBackground.svelte'
	import LightBendsBackground from './webgl/LightBendsBackground.svelte'
	import LightRaysBackground from './webgl/LightRaysBackground.svelte'
	import SilkBackground from './webgl/SilkBackground.svelte'

	export type BackgroundType =
		| 'galaxy'
		| 'darkveil'
		| 'lightbends'
		| 'lightrays'
		| 'silk'
		| 'fog'
		| 'clouds'
		| 'clouds-dark'
		| 'clouds2'
		| 'clouds2-dark'
		| 'grainient'
		| 'iridescence'
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
	}

	interface Props {
		type: BackgroundType
		config?: BackgroundConfig
		children?: Snippet
		onReady?: () => void
	}

	let { type = 'galaxy', config = {}, children, onReady }: Props = $props()

	let readySent = $state(false)
	function signalReady() {
		if (readySent) return
		readySent = true
		onReady?.()
	}

	// Transition state for smooth swapping
	let currentBg = $state<BackgroundType>('galaxy')
	currentBg = untrack(() => type)
	let previousBg = $state<BackgroundType | null>(null)
	let isTransitioning = $state(false)

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
		if (readySent) return
		if (currentBg === 'static' || currentBg === 'none') {
			signalReady()
		}
	})
</script>

<!-- Background layers - positioned absolutely -->
<div class="fixed inset-0 -z-10">
	{#if previousBg && isTransitioning}
		<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
			{#if previousBg === 'galaxy'}
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
				/>
			{:else if previousBg === 'darkveil'}
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
			{:else if previousBg === 'lightbends'}
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
			{:else if previousBg === 'lightrays'}
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
			{:else if previousBg === 'silk'}
				<SilkBackground color={resolvedConfig.silkColor} speed={resolvedConfig.silkSpeed} />
			{:else if previousBg === 'fog'}
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
			{:else if previousBg === 'clouds' || previousBg === 'clouds-dark'}
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
			{:else if previousBg === 'clouds2' || previousBg === 'clouds2-dark'}
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
			{:else if previousBg === 'grainient'}
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
			{:else if previousBg === 'iridescence'}
				<IridescenceBackground
					color={resolvedConfig.iridescenceColor}
					speed={resolvedConfig.iridescenceSpeed}
					amplitude={resolvedConfig.iridescenceAmplitude}
					mouseReact={resolvedConfig.iridescenceMouseReact}
				/>
			{:else if previousBg === 'static'}
				<StaticBackground color={resolvedConfig.color} image={resolvedConfig.image} />
			{/if}
		</div>
	{/if}

	<div class="absolute inset-0" style="opacity: 1; transition: opacity 300ms ease-in-out;">
		{#if currentBg === 'galaxy'}
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
				onReady={signalReady}
			>
				{#if children}{@render children()}{/if}
			</GalaxyBackgroundWebGL>
		{:else if currentBg === 'darkveil'}
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
			>
				{#if children}{@render children()}{/if}
			</DarkVeilBackground>
		{:else if currentBg === 'lightbends'}
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
			>
				{#if children}{@render children()}{/if}
			</LightBendsBackground>
		{:else if currentBg === 'lightrays'}
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
			>
				{#if children}{@render children()}{/if}
			</LightRaysBackground>
		{:else if currentBg === 'silk'}
			<SilkBackground
				color={resolvedConfig.silkColor}
				speed={resolvedConfig.silkSpeed}
				onReady={signalReady}
			>
				{#if children}{@render children()}{/if}
			</SilkBackground>
		{:else if currentBg === 'fog'}
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
			>
				{#if children}{@render children()}{/if}
			</FogBackground>
		{:else if currentBg === 'clouds'}
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
			>
				{#if children}{@render children()}{/if}
			</CloudsBackground>
		{:else if currentBg === 'clouds-dark'}
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
			>
				{#if children}{@render children()}{/if}
			</CloudsBackground>
		{:else if currentBg === 'clouds2'}
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
			>
				{#if children}{@render children()}{/if}
			</Clouds2Background>
		{:else if currentBg === 'clouds2-dark'}
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
			>
				{#if children}{@render children()}{/if}
			</Clouds2Background>
		{:else if currentBg === 'grainient'}
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
			>
				{#if children}{@render children()}{/if}
			</GrainientBackground>
		{:else if currentBg === 'iridescence'}
			<IridescenceBackground
				color={resolvedConfig.iridescenceColor}
				speed={resolvedConfig.iridescenceSpeed}
				amplitude={resolvedConfig.iridescenceAmplitude}
				mouseReact={resolvedConfig.iridescenceMouseReact}
				onReady={signalReady}
			>
				{#if children}{@render children()}{/if}
			</IridescenceBackground>
		{:else if currentBg === 'static'}
			<StaticBackground color={resolvedConfig.color} image={resolvedConfig.image}>
				{#if children}{@render children()}{/if}
			</StaticBackground>
		{:else if currentBg === 'none' && children}
			<div class="relative z-1">
				{@render children()}
			</div>
		{/if}
	</div>
</div>
