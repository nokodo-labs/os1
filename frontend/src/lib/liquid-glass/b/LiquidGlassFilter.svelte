<script lang="ts">
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
		/** thickness of the flat glass body beyond the bezel (px) — main displacement control */
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
	}

	let {
		filterId,
		width,
		height,
		bezelWidth = 20,
		thickness = 40,
		cornerRadius,
		surfaceFn = squircleSurface,
		refractionStrength = 1.0,
		innerRefraction = 0.12,
		glassThickness = 40,
		blurRadius = 0.2,
		specularOpacity = 1.0,
		specularSaturation = 4,
		specularAngle = 315,
		specularFalloff = 1.0,
	}: Props = $props()

	let displacementUrl = $state('')
	let specularUrl = $state('')
	let maxDisplacement = $state(1)
	let resolvedCornerRadius = $derived(cornerRadius ?? Math.min(width, height) / 2)

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
		regenerateMaps()
	})

	// scale = maxDisplacement * refractionStrength (matches reference: maximumDisplacement * scaleRatio)
	// the SVG spec gives offset = scale × (channel/255 − 0.5), range [−scale/2, +scale/2].
	// at max encoded ±127/255, actual offset ≈ ±scale*0.498 ≈ ±maxDisplacement*0.5
	const computedScale = $derived(maxDisplacement * refractionStrength)
	const filterPadding = $derived(Math.max(bezelWidth, blurRadius * 2))
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
			<!-- 1. blur source before displacement (reference: single blur) -->
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

			<!-- 3. apply refraction displacement -->
			<feDisplacementMap
				in="blurred"
				in2="dispMap"
				scale={computedScale}
				xChannelSelector="R"
				yChannelSelector="G"
				result="displaced"
			/>

			<!-- 4. boost color saturation on displaced image -->
			<feColorMatrix
				in="displaced"
				type="saturate"
				values={specularSaturation.toString()}
				result="displaced_saturated"
			/>

			<!-- 5. specular highlight image -->
			<feImage
				href={specularUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="specular_layer"
				preserveAspectRatio="none"
			/>

			<!-- 6. clip saturated displaced to specular shape (saturation only where highlight exists) -->
			<feComposite
				in="displaced_saturated"
				in2="specular_layer"
				operator="in"
				result="specular_saturated"
			/>

			<!-- 7. fade specular highlight by opacity -->
			<feComponentTransfer in="specular_layer" result="specular_faded">
				<feFuncA type="linear" slope={specularOpacity} />
			</feComponentTransfer>

			<!-- 8. blend saturated specular region back onto displaced -->
			<feBlend
				in="specular_saturated"
				in2="displaced"
				mode="normal"
				result="withSaturation"
			/>

			<!-- 9. blend faded specular highlight on top -->
			<feBlend in="specular_faded" in2="withSaturation" mode="normal" />
		</filter>
	</defs>
</svg>
