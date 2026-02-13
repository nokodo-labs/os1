<script lang="ts">
	import LiquidGlassFilter from '$lib/liquid-glass/b/LiquidGlassFilter.svelte'

	interface Props {
		size?: 'xs' | 'sm' | 'md' | 'lg'
		min?: number
		max?: number
		step?: number
		value?: number
		onchange?: (value: number) => void
		disabled?: boolean
		forceActive?: boolean
		glassThickness?: number
		bezelWidth?: number
		refractiveIndex?: number
	}

	const SIZES = {
		xs: {
			thumb: { width: 35, height: 20 },
			slider: { width: 135, height: 5 },
			glassThickness: 40,
			bezelWidth: 8,
		},
		sm: {
			thumb: { width: 52, height: 30 },
			slider: { width: 202, height: 7 },
			glassThickness: 60,
			bezelWidth: 12,
		},
		md: {
			thumb: { width: 70, height: 40 },
			slider: { width: 270, height: 10 },
			glassThickness: 80,
			bezelWidth: 16,
		},
		lg: {
			thumb: { width: 87, height: 50 },
			slider: { width: 337, height: 12 },
			glassThickness: 100,
			bezelWidth: 20,
		},
	} as const

	const SCALE_REST = 0.6
	const SCALE_DRAG = 1

	let {
		size = 'md',
		min = 0,
		max = 100,
		step = 1,
		value = $bindable(50),
		onchange,
		disabled = false,
		forceActive = false,
		glassThickness: customGlassThickness,
		bezelWidth: customBezelWidth,
		refractiveIndex = 1.5,
	}: Props = $props()

	const sizeConfig = $derived(SIZES[size])
	const thumbW = $derived(sizeConfig.thumb.width)
	const thumbH = $derived(sizeConfig.thumb.height)
	const sliderW = $derived(sizeConfig.slider.width)
	const sliderH = $derived(sizeConfig.slider.height)
	const glassThick = $derived(customGlassThickness ?? sizeConfig.glassThickness)
	const bezel = $derived(customBezelWidth ?? sizeConfig.bezelWidth)
	const thumbRadius = $derived(thumbH / 2)

	const filterId = `slider-thumb-${Math.random().toString(36).slice(2, 8)}`

	let isPressed = $state(false)
	let trackEl: HTMLDivElement | null = $state(null)

	const active = $derived(forceActive || isPressed)
	const thumbScale = $derived(active ? SCALE_DRAG : SCALE_REST)
	const thumbWidthRest = $derived(thumbW * SCALE_REST)
	const scaleRatio = $derived((active ? 0.9 : 0.4) * 1.0)

	const ratio = $derived((value - min) / (max - min))
	// travel = full range of the thumb center, accounting for visual thumb width at rest scale
	const travel = $derived(sliderW - thumbWidthRest)
	// position so visual thumb edges align with track edges at min/max
	const thumbLeft = $derived(ratio * travel - (thumbW - thumbWidthRest) / 2)

	const bgOpacity = $derived(active ? 0.1 : 1)

	function updateValueFromPointer(clientX: number) {
		if (!trackEl) return
		const rect = trackEl.getBoundingClientRect()
		const x0 = rect.left + thumbWidthRest / 2
		const x100 = rect.right - thumbWidthRest / 2
		const insideWidth = x100 - x0
		const r = Math.max(0, Math.min(1, (clientX - x0) / insideWidth))
		const raw = r * (max - min) + min
		const stepped = Math.round(raw / step) * step
		value = Math.max(min, Math.min(max, stepped))
		onchange?.(value)
	}

	function handlePointerDown(e: PointerEvent) {
		if (disabled) return
		isPressed = true
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
		updateValueFromPointer(e.clientX)
	}

	function handlePointerMove(e: PointerEvent) {
		if (!isPressed || disabled) return
		updateValueFromPointer(e.clientX)
	}

	function handlePointerUp(e: PointerEvent) {
		isPressed = false
		if (e.currentTarget instanceof HTMLElement) {
			e.currentTarget.releasePointerCapture(e.pointerId)
		}
	}
</script>

<LiquidGlassFilter
	{filterId}
	width={thumbW}
	height={thumbH}
	cornerRadius={thumbRadius}
	glassThickness={glassThick}
	bezelWidth={bezel}
	refractionStrength={scaleRatio}
	blurRadius={0}
	specularOpacity={0.4}
	specularSaturation={7}
/>

<div
	class="relative"
	style="width: {sliderW}px; height: {thumbH}px;"
	role="slider"
	aria-valuemin={min}
	aria-valuemax={max}
	aria-valuenow={value}
	tabindex="0"
	onkeydown={(e) => {
		if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
			e.preventDefault()
			value = Math.min(max, value + step)
			onchange?.(value)
		} else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
			e.preventDefault()
			value = Math.max(min, value - step)
			onchange?.(value)
		}
	}}
>
	<!-- track -->
	<div
		bind:this={trackEl}
		role="presentation"
		class="absolute cursor-pointer"
		style="
			width: {sliderW}px;
			height: {sliderH}px;
			top: {(thumbH - sliderH) / 2}px;
			background-color: #89898F66;
			border-radius: {sliderH / 2}px;
		"
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerUp}
	>
		<!-- fill -->
		<div class="h-full overflow-hidden rounded-full">
			<div
				style="
					height: {sliderH}px;
					width: {ratio * 100}%;
					background-color: #0377F7;
					border-radius: 6px;
				"
			></div>
		</div>
	</div>

	<!-- thumb -->
	<div
		role="presentation"
		class="absolute cursor-pointer"
		style="
			width: {thumbW}px;
			height: {thumbH}px;
			top: 0;
			left: {thumbLeft}px;
			border-radius: {thumbRadius}px;
			backdrop-filter: url(#{filterId});
			-webkit-backdrop-filter: url(#{filterId});
			transform: scale({thumbScale});
			transition: transform 200ms cubic-bezier(0.4, 0, 0.2, 1);
			background-color: rgba(255, 255, 255, {bgOpacity});
			box-shadow: 0 3px 14px rgba(0,0,0,0.1);
		"
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerUp}
	></div>
</div>
