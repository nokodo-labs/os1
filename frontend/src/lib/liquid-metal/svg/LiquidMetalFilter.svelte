<script lang="ts">
	import { generateDisplacementMap } from './displacement-map'
	import { squircleSurface, type SurfaceFunction } from './physics'
	import { generateSpecularHighlight } from './specular'

	interface Props {
		filterId: string
		width: number
		height: number
		bezelWidth?: number
		thickness?: number
		cornerRadius?: number
		surfaceFn?: SurfaceFunction
		refractionStrength?: number
		mirrorDepth?: number
		specularOpacity?: number
		specularAngle?: number
		specularFalloff?: number
	}

	let {
		filterId,
		width,
		height,
		bezelWidth = 20,
		thickness = 18,
		cornerRadius,
		surfaceFn = squircleSurface,
		refractionStrength = 1.4,
		mirrorDepth = 26,
		specularOpacity = 0.9,
		specularAngle = 320,
		specularFalloff = 1.15,
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
			mirrorDepth,
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
			mirrorDepth,
			specularAngle,
			specularFalloff,
		]

		if (debounceTimer) clearTimeout(debounceTimer)

		if (!displacementUrl) {
			regenerateMaps()
		} else {
			debounceTimer = setTimeout(() => {
				regenerateMaps()
			}, 120)
		}

		return () => {
			if (debounceTimer) clearTimeout(debounceTimer)
		}
	})

	const computedScale = $derived(maxDisplacement * refractionStrength)
	const filterPadding = $derived(Math.max(bezelWidth, 6))
</script>

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
			color-interpolation-filters="sRGB"
		>
			<feImage
				href={displacementUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="dispMap"
				preserveAspectRatio="none"
			/>

			<feImage
				href={specularUrl}
				x="0"
				y="0"
				{width}
				{height}
				result="specularRaw"
				preserveAspectRatio="none"
			/>

			<feDisplacementMap
				in="specularRaw"
				in2="dispMap"
				scale={computedScale}
				xChannelSelector="R"
				yChannelSelector="G"
				result="specularWarped"
			/>

			<feComponentTransfer in="specularWarped" result="specularDim">
				<feFuncA type="linear" slope={specularOpacity} />
			</feComponentTransfer>

			<feComposite in="specularDim" in2="SourceAlpha" operator="in" result="specularMasked" />

			<feBlend in="SourceGraphic" in2="specularMasked" mode="screen" result="finalOut" />
		</filter>
	</defs>
</svg>
