<script lang="ts">
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
	}

	const SIZES = {
		xs: { thumb: { width: 35, height: 20 }, slider: { width: 135, height: 5 } },
		sm: { thumb: { width: 52, height: 30 }, slider: { width: 202, height: 7 } },
		md: { thumb: { width: 70, height: 40 }, slider: { width: 270, height: 10 } },
		lg: { thumb: { width: 87, height: 50 }, slider: { width: 337, height: 12 } },
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
	}: Props = $props()

	const sizeConfig = $derived(SIZES[size])
	const thumbW = $derived(sizeConfig.thumb.width)
	const thumbH = $derived(sizeConfig.thumb.height)
	const sliderW = $derived(sizeConfig.slider.width)
	const sliderH = $derived(sizeConfig.slider.height)
	const thumbRadius = $derived(thumbH / 2)

	let isPressed = $state(false)
	let trackEl: HTMLDivElement | null = $state(null)

	const active = $derived(forceActive || isPressed)
	const thumbScale = $derived(active ? SCALE_DRAG : SCALE_REST)
	const thumbWidthRest = $derived(thumbW * SCALE_REST)

	const ratio = $derived((value - min) / (max - min))
	const travel = $derived(sliderW - thumbWidthRest)
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

<div
	class="relative"
	style="width: {sliderW}px; height: {thumbH}px; touch-action: none;"
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

	<div
		role="presentation"
		class="liquid-glass absolute cursor-pointer"
		style="
			width: {thumbW}px;
			height: {thumbH}px;
			top: 0;
			left: {thumbLeft}px;
			border-radius: {thumbRadius}px;
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
