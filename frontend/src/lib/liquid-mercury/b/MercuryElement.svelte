<script lang="ts">
	import type { Snippet } from 'svelte'
	import LiquidMercuryFilter from './LiquidMercuryFilter.svelte'
	import { circularSurface, lipSurface, squircleSurface } from './physics'

	interface Props {
		width?: number
		height?: number
		bezelWidth?: number
		thickness?: number
		borderRadius?: string
		surface?: 'squircle' | 'circular' | 'lip'
		class?: string
		children?: Snippet
	}

	let {
		width = 200,
		height = 200,
		bezelWidth = 20,
		thickness = 18,
		borderRadius = '24px',
		surface = 'squircle',
		class: className = '',
		children,
	}: Props = $props()

	const filterId = `lm-${Math.random().toString(36).substring(2, 11)}`

	const surfaceMap = {
		squircle: squircleSurface,
		circular: circularSurface,
		lip: lipSurface,
	} as const
</script>

<LiquidMercuryFilter
	{filterId}
	{width}
	{height}
	{bezelWidth}
	{thickness}
	surfaceFn={surfaceMap[surface]}
/>

<div
	class="liquid-mercury {className}"
	style:width="{width}px"
	style:height="{height}px"
	style:border-radius={borderRadius}
	style:filter="url(#{filterId})"
>
	{@render children?.()}
</div>
