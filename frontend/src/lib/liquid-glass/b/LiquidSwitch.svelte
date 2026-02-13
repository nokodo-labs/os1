<script lang="ts">
	import LiquidGlassFilter from './LiquidGlassFilter.svelte'
	import { lipSurface } from './physics'

	interface Props {
		size?: 'sm' | 'md' | 'lg' | 'xl'
		checked?: boolean
		onchange?: (checked: boolean) => void
		disabled?: boolean
		forceActive?: boolean
		glassThickness?: number
		bezelWidth?: number
		refractiveIndex?: number
		blur?: number
		specularOpacity?: number
		specularSaturation?: number
	}

	const SIZES = {
		sm: {
			thumb: { width: 48, height: 30 },
			slider: { width: 60, height: 24 },
			glassThickness: 24,
			bezelWidth: 10,
		},
		md: {
			thumb: { width: 73, height: 46 },
			slider: { width: 80, height: 34 },
			glassThickness: 24,
			bezelWidth: 10,
		},
		lg: {
			thumb: { width: 109, height: 69 },
			slider: { width: 120, height: 50 },
			glassThickness: 35,
			bezelWidth: 14,
		},
		xl: {
			thumb: { width: 146, height: 92 },
			slider: { width: 160, height: 67 },
			glassThickness: 47,
			bezelWidth: 19,
		},
	} as const

	const THUMB_REST_SCALE = 0.65
	const THUMB_ACTIVE_SCALE = 0.9

	let {
		size = 'md',
		checked = $bindable(false),
		onchange,
		disabled = false,
		forceActive = false,
		glassThickness: customGlassThickness,
		bezelWidth: customBezelWidth,
		refractiveIndex = 1.5,
		blur = 0.2,
		specularOpacity = 0.5,
		specularSaturation = 6,
	}: Props = $props()

	const sizeConfig = $derived(SIZES[size])
	const thumbW = $derived(sizeConfig.thumb.width)
	const thumbH = $derived(sizeConfig.thumb.height)
	const sliderW = $derived(sizeConfig.slider.width)
	const sliderH = $derived(sizeConfig.slider.height)
	const glassThick = $derived(customGlassThickness ?? sizeConfig.glassThickness)
	const bezel = $derived(customBezelWidth ?? sizeConfig.bezelWidth)
	const thumbRadius = $derived(thumbH / 2)

	const filterId = `switch-thumb-${Math.random().toString(36).slice(2, 8)}`

	let isPressed = $state(false)
	let isDragging = $state(false)
	let startX = 0
	let dragRatio = $state(0)

	const active = $derived(forceActive || isPressed)
	const thumbScale = $derived(active ? THUMB_ACTIVE_SCALE : THUMB_REST_SCALE)
	const scaleRatio = $derived((active ? 0.9 : 0.4) * 1.0)

	const THUMB_REST_OFFSET = $derived(((1 - THUMB_REST_SCALE) * thumbW) / 2)
	const TRAVEL = $derived(sliderW - sliderH - (thumbW - thumbH) * THUMB_REST_SCALE)

	const thumbX = $derived(() => {
		if (isDragging) {
			return Math.max(0, Math.min(1, dragRatio)) * TRAVEL
		}
		return (checked ? 1 : 0) * TRAVEL
	})

	const bgColor = $derived(checked ? '#3BBF4EEE' : '#94949F77')
	const bgOpacity = $derived(active ? 0.1 : 1)

	function toggle() {
		if (disabled) return
		checked = !checked
		onchange?.(checked)
	}

	function handlePointerDown(e: PointerEvent) {
		if (disabled) return
		e.stopPropagation()
		isPressed = true
		startX = e.clientX
		dragRatio = checked ? 1 : 0
		;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
	}

	function handlePointerMove(e: PointerEvent) {
		if (!isPressed || disabled) return
		const dx = e.clientX - startX
		if (Math.abs(dx) > 4) isDragging = true
		const base = checked ? 1 : 0
		dragRatio = Math.max(0, Math.min(1, base + dx / TRAVEL))
	}

	function handlePointerUp(e: PointerEvent) {
		if (!isPressed) return
		if (isDragging) {
			const shouldBeChecked = dragRatio > 0.5
			if (shouldBeChecked !== checked) {
				checked = shouldBeChecked
				onchange?.(checked)
			}
		} else {
			toggle()
		}
		isPressed = false
		isDragging = false
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
	blurRadius={blur}
	{specularOpacity}
	{specularSaturation}
	surfaceFn={lipSurface}
/>

<div
	class="relative"
	style="width: {sliderW}px; height: {sliderH}px;"
	role="switch"
	aria-checked={checked}
	tabindex="0"
	onkeydown={(e) => {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault()
			toggle()
		}
	}}
>
	<!-- rail -->
	<div
		role="presentation"
		class="absolute inset-0 cursor-pointer rounded-full"
		style="background-color: {bgColor}; transition: background-color 200ms;"
		onclick={toggle}
	></div>

	<!-- thumb -->
	<div
		role="presentation"
		class="absolute cursor-pointer"
		style="
			width: {thumbW}px;
			height: {thumbH}px;
			top: 50%;
			left: {-THUMB_REST_OFFSET + (sliderH - thumbH * THUMB_REST_SCALE) / 2}px;
			transform: translateY(-50%) translateX({thumbX()}px) scale({thumbScale});
			transition: {isDragging ? 'none' : 'transform 300ms cubic-bezier(0.4, 0, 0.2, 1)'};
			border-radius: {thumbRadius}px;
			backdrop-filter: url(#{filterId});
			-webkit-backdrop-filter: url(#{filterId});
			background-color: rgba(255, 255, 255, {bgOpacity});
			box-shadow: 0 4px 22px rgba(0,0,0,0.1){isPressed
			? ', inset 2px 7px 24px rgba(0,0,0,0.09), inset -2px -7px 24px rgba(255,255,255,0.09)'
			: ''};
		"
		onpointerdown={handlePointerDown}
		onpointermove={handlePointerMove}
		onpointerup={handlePointerUp}
		onpointercancel={handlePointerUp}
	></div>
</div>
