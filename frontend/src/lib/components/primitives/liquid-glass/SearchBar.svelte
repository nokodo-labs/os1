<script lang="ts">
	import LiquidGlassFilter from '$lib/liquid-glass/b/LiquidGlassFilter.svelte'

	interface Props {
		placeholder?: string
		value?: string
		width?: number
		height?: number
		glassThickness?: number
		bezelWidth?: number
		disabled?: boolean
	}

	let {
		placeholder = 'search...',
		value = $bindable(''),
		width = 320,
		height = 48,
		glassThickness = 30,
		bezelWidth = 12,
		disabled = false,
	}: Props = $props()

	const filterId = `search-bar-${Math.random().toString(36).slice(2, 8)}`
	const radius = $derived(height / 2)

	let isFocused = $state(false)

	const REST_SCALE = 0.95
	const FOCUS_SCALE = 1.02
	const scale = $derived(isFocused ? FOCUS_SCALE : REST_SCALE)
	const bgOpacity = $derived(isFocused ? 0.2 : 0.04)
	const scaleRatio = $derived(isFocused ? 0.8 : 0.4)
</script>

<LiquidGlassFilter
	{filterId}
	{width}
	{height}
	cornerRadius={radius}
	{glassThickness}
	{bezelWidth}
	refractionStrength={scaleRatio}
	blurRadius={0.2}
	specularOpacity={0.6}
	specularSaturation={5}
/>

<div
	class="relative"
	style="
		width: {width}px;
		height: {height}px;
		border-radius: {radius}px;
		backdrop-filter: url(#{filterId});
		-webkit-backdrop-filter: url(#{filterId});
		transform: scale({scale});
		transition: transform 400ms cubic-bezier(0.34, 1.56, 0.64, 1), background-color 300ms ease;
		background-color: rgba(255, 255, 255, {bgOpacity});
		box-shadow: 0 2px 12px rgba(0,0,0,0.08);
	"
>
	<!-- search icon -->
	<svg
		class="text-foreground/40 pointer-events-none absolute top-1/2 left-4 -translate-y-1/2"
		width="18"
		height="18"
		viewBox="0 0 24 24"
		fill="none"
		stroke="currentColor"
		stroke-width="2"
		stroke-linecap="round"
		stroke-linejoin="round"
	>
		<circle cx="11" cy="11" r="8" />
		<path d="m21 21-4.3-4.3" />
	</svg>

	<input
		type="text"
		bind:value
		{placeholder}
		{disabled}
		onfocus={() => (isFocused = true)}
		onblur={() => (isFocused = false)}
		class="text-foreground/80 placeholder:text-foreground/40 h-full w-full bg-transparent pr-4 pl-11 text-sm outline-none"
		style="border-radius: {radius}px;"
	/>
</div>
