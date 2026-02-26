<script lang="ts">
	import { useTheme } from '$lib/contexts/themeContext.svelte'
	import { generateDisplacementMap } from './displacement-map'
	import type { SurfaceFunction } from './physics'
	import { squircleSurface } from './physics'
	import { generateSpecularHighlight } from './specular'

	interface Props {
		filterId: string
		width: number
		height: number
		bezelWidth?: number
		thickness?: number
		cornerRadius?: number
		surfaceFn?: SurfaceFunction
		/** multiplier on the displacement scale (1.0 = physics-accurate) */
		refractionStrength?: number
		/** normalized refraction strength for the flat interior (0-1) */
		innerRefraction?: number
		/** thickness of the flat glass body beyond the bezel (px) - main displacement control */
		glassThickness?: number
		/** gaussian blur radius applied before displacement (px) */
		blurRadius?: number
		/** specular highlight intensity (0-1) */
		specularOpacity?: number
		/** color saturation boost in specular region (1 = no boost) */
		specularSaturation?: number
		/** specular highlight light angle in degrees */
		specularAngle?: number
		/** specular highlight falloff exponent */
		specularFalloff?: number
		/** chromatic aberration strength (0 = off, 0.03-0.1 = subtle, >0.1 = strong) */
		chromaticAberration?: number
		/** subtle glass body tint brightness boost (0 = off, 0.02-0.05 = subtle) */
		glassTint?: number
	}

	let {
		filterId,
		width,
		height,
		bezelWidth = 44,
		thickness = 33,
		cornerRadius,
		surfaceFn = squircleSurface,
		refractionStrength = 1.8,
		innerRefraction = 0,
		glassThickness = 140,
		blurRadius = 0.3,
		specularOpacity = 1.0,
		specularSaturation = 4,
		specularAngle = 315,
		specularFalloff = 1.0,
		chromaticAberration = 0.13,
		glassTint = 0.08,
	}: Props = $props()

	let displacementUrl = $state('')
	let specularUrl = $state('')
	let maxDisplacement = $state(1)
	let resolvedCornerRadius = $derived(cornerRadius ?? Math.min(width, height) / 2)

	let debounceTimer: ReturnType<typeof setTimeout> | null = null

	function regenerateMaps() {
		if (width <= 0 || height <= 0) return

		const displacement = generateDisplacementMap({
			width,
			height,
			bezelWidth,
			thickness,
			surfaceFn,
			cornerRadius: resolvedCornerRadius,
			innerRefraction,
			glassThickness,
		})

		displacementUrl = displacement.imageDataUrl
		maxDisplacement = displacement.maxDisplacement

		specularUrl = generateSpecularHighlight({
			width,
			height,
			bezelWidth,
			cornerRadius: resolvedCornerRadius,
			intensity: 1,
			lightAngle: specularAngle,
			falloff: specularFalloff,
		})
	}

	$effect(() => {
		void [
			width,
			height,
			bezelWidth,
			thickness,
			cornerRadius,
			innerRefraction,
			glassThickness,
			specularAngle,
			specularFalloff,
		]

		if (debounceTimer) clearTimeout(debounceTimer)

		// if we don't have a map yet, generate immediately
		if (!displacementUrl) {
			regenerateMaps()
		} else {
			// debounce during animations (e.g. island expanding)
			debounceTimer = setTimeout(() => {
				regenerateMaps()
			}, 150)
		}

		return () => {
			if (debounceTimer) clearTimeout(debounceTimer)
		}
	})

	// scale = maxDisplacement * refractionStrength (matches reference: maximumDisplacement * scaleRatio)
	// the SVG spec gives offset = scale × (channel/255 − 0.5), range [−scale/2, +scale/2].
	// at max encoded ±127/255, actual offset ≈ ±scale*0.498 ≈ ±maxDisplacement*0.5
	const computedScale = $derived(maxDisplacement * refractionStrength)
	const filterPadding = $derived(Math.max(bezelWidth, blurRadius * 2))
	const caEnabled = $derived(chromaticAberration > 0)
	// chromatic aberration scale offsets for R (over-refracted) and B (under-refracted)
	const scaleR = $derived(computedScale * (1 + chromaticAberration))
	const scaleB = $derived(computedScale * (1 - chromaticAberration))
	const theme = useTheme()
	const tintAmount = $derived(Math.abs(glassTint))
	const tintSigned = $derived((theme.resolvedMode === 'dark' ? -1 : 1) * tintAmount)
	// glass tint: brighten in light mode, darken in dark mode
	const tintSlope = $derived(1 + tintSigned)
	const tintIntercept = $derived(tintSigned * 0.3)
</script>

<!--
	colorInterpolationFilters="sRGB" is CRITICAL.
	without it, the browser uses linearRGB which gamma-transforms
	the 128 neutral value to ~0.216, completely destroying displacement.
-->
<svg width="0" height="0" style="position: absolute;" color-interpolation-filters="sRGB">
	<defs>
		<filter
			id={filterId}
			x={-filterPadding}
			y={-filterPadding}
			width={width + filterPadding * 2}
			height={height + filterPadding * 2}
			filterUnits="userSpaceOnUse"
			primitiveUnits="userSpaceOnUse"
		>
			<!-- 1. blur source before displacement -->
			<feGaussianBlur in="SourceGraphic" stdDeviation={blurRadius} result="blurred" />

			<!-- 2. displacement map image -->
			<feImage
				href={displacementUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="dispMap"
				preserveAspectRatio="none"
			/>

			{#if caEnabled}
				<!-- 3a. chromatic aberration: 3 displacements at different scales -->
				<feDisplacementMap
					in="blurred"
					in2="dispMap"
					scale={scaleR}
					xChannelSelector="R"
					yChannelSelector="G"
					result="d_over"
				/>
				<feDisplacementMap
					in="blurred"
					in2="dispMap"
					scale={computedScale}
					xChannelSelector="R"
					yChannelSelector="G"
					result="d_base"
				/>
				<feDisplacementMap
					in="blurred"
					in2="dispMap"
					scale={scaleB}
					xChannelSelector="R"
					yChannelSelector="G"
					result="d_under"
				/>

				<!-- isolate R from over-displaced, G from base, B from under-displaced -->
				<feColorMatrix
					in="d_over"
					type="matrix"
					values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
					result="r_ch"
				/>
				<feColorMatrix
					in="d_base"
					type="matrix"
					values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0"
					result="g_ch"
				/>
				<feColorMatrix
					in="d_under"
					type="matrix"
					values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"
					result="b_ch"
				/>

				<!-- recombine channels via screen blend (non-overlapping channels add correctly) -->
				<feBlend in="r_ch" in2="g_ch" mode="screen" result="rg_ch" />
				<feBlend in="rg_ch" in2="b_ch" mode="screen" result="displaced" />
			{:else}
				<!-- 3b. standard single displacement -->
				<feDisplacementMap
					in="blurred"
					in2="dispMap"
					scale={computedScale}
					xChannelSelector="R"
					yChannelSelector="G"
					result="displaced"
				/>
			{/if}

			<!-- 4. subtle glass body brightness/tint for depth (makes interior less purely transparent) -->
			{#if tintAmount > 0}
				<feComponentTransfer in="displaced" result="displaced">
					<feFuncR type="linear" slope={tintSlope} intercept={tintIntercept} />
					<feFuncG type="linear" slope={tintSlope} intercept={tintIntercept} />
					<feFuncB type="linear" slope={tintSlope} intercept={tintIntercept} />
				</feComponentTransfer>
			{/if}

			<!-- 5. boost color saturation on displaced image -->
			<feColorMatrix
				in="displaced"
				type="saturate"
				values={specularSaturation.toString()}
				result="displaced_saturated"
			/>

			<!-- 6. specular highlight image -->
			<feImage
				href={specularUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="specular_layer"
				preserveAspectRatio="none"
			/>

			<!-- 7. clip saturated displaced to specular shape -->
			<feComposite
				in="displaced_saturated"
				in2="specular_layer"
				operator="in"
				result="specular_saturated"
			/>

			<!-- 8. fade specular highlight by opacity -->
			<feComponentTransfer in="specular_layer" result="specular_faded">
				<feFuncA type="linear" slope={specularOpacity} />
			</feComponentTransfer>

			<!-- 9. blend saturated specular region back onto displaced -->
			<feBlend
				in="specular_saturated"
				in2="displaced"
				mode="normal"
				result="withSaturation"
			/>

			<!-- 10. blend faded specular highlight on top -->
			<feBlend in="specular_faded" in2="withSaturation" mode="normal" />
		</filter>
	</defs>
</svg>
