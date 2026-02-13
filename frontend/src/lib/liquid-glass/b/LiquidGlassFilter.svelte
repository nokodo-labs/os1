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
		/** multiplier on top of physics-based displacement (crank for stronger edges) */
		refractionStrength?: number
		/** gaussian blur radius for the flat interior (px) */
		blurRadius?: number
		/** specular highlight intensity (0-1) */
		specularOpacity?: number
		/** specular highlight light angle in degrees */
		specularAngle?: number
		/** specular highlight falloff exponent */
		specularFalloff?: number
		/** semi-transparent background overlay opacity (0-1) */
		glassBgOpacity?: number
	}

	let {
		filterId,
		width,
		height,
		bezelWidth = 40,
		thickness = 40,
		cornerRadius,
		surfaceFn = squircleSurface,
		refractionStrength = 2.0,
		blurRadius = 2,
		specularOpacity = 0.4,
		specularAngle = 315,
		specularFalloff = 2.0,
		glassBgOpacity = 0.06,
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
		})

		displacementUrl = displacement.imageDataUrl
		maxDisplacement = displacement.maxDisplacement

		specularUrl = generateSpecularHighlight({
			width,
			height,
			bezelWidth,
			cornerRadius: resolvedCornerRadius,
			intensity: 1, // full strength, we control via feComponentTransfer
			lightAngle: specularAngle,
			falloff: specularFalloff,
		})
	}

	$effect(() => {
		void [width, height, bezelWidth, thickness, cornerRadius, specularAngle, specularFalloff]
		regenerateMaps()
	})

	// SVG spec: offset = scale × (channel/255 − 0.5), so range is [−scale/2, +scale/2].
	// our max encoded value maps to scale/2 pixels — double to get full maxDisplacement.
	const computedScale = $derived(maxDisplacement * refractionStrength * 2)
</script>

<!--
	colorInterpolationFilters="sRGB" is CRITICAL.
	without it, the browser uses linearRGB which gamma-transforms
	the 128 neutral value to ~0.216, completely destroying displacement.
-->
<svg width="0" height="0" style="position: absolute;" color-interpolation-filters="sRGB">
	<defs>
		<filter id={filterId} x="-5%" y="-5%" width="110%" height="110%">
			<!-- 1. displacement map image -->
			<feImage
				href={displacementUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="dispMap"
				preserveAspectRatio="none"
			/>

			<!-- 2. apply refraction displacement to the SHARP source (not blurred!) -->
			<feDisplacementMap
				in="SourceGraphic"
				in2="dispMap"
				scale={computedScale}
				xChannelSelector="R"
				yChannelSelector="G"
				result="refracted"
			/>

			<!-- 3. light blur AFTER displacement — softens the refracted image for glass feel -->
			<feGaussianBlur in="refracted" stdDeviation={blurRadius} result="blurred" />

			<!-- 4. tint overlay: semi-transparent white fill for glass body -->
			<feFlood flood-color="white" flood-opacity={glassBgOpacity} result="tint" />
			<feComposite in="tint" in2="blurred" operator="over" result="tinted" />

			<!-- 5. specular highlight image, controlled by opacity -->
			<feImage
				href={specularUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="specRaw"
				preserveAspectRatio="none"
			/>
			<!-- scale specular intensity -->
			<feComponentTransfer in="specRaw" result="specular">
				<feFuncA type="linear" slope={specularOpacity} />
			</feComponentTransfer>

			<!-- 6. composite specular on top -->
			<feComposite in="specular" in2="tinted" operator="over" result="final" />
		</filter>
	</defs>
</svg>
