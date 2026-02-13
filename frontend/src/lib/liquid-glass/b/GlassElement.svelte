<script lang="ts">
	import type { Snippet } from 'svelte'
	import LiquidGlassFilter from './LiquidGlassFilter.svelte'
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
		bezelWidth = 40,
		thickness = 20,
		borderRadius = '24px',
		surface = 'squircle',
		class: className = '',
		children,
	}: Props = $props()

	const filterId = `lg2-${Math.random().toString(36).substring(2, 11)}`

	const surfaceMap = {
		squircle: squircleSurface,
		circular: circularSurface,
		lip: lipSurface,
	} as const
</script>

<LiquidGlassFilter
	{filterId}
	{width}
	{height}
	{bezelWidth}
	{thickness}
	surfaceFn={surfaceMap[surface]}
/>

<div
	class="lg2-element {className}"
	style:width="{width}px"
	style:height="{height}px"
	style:border-radius={borderRadius}
	style:backdrop-filter="url(#{filterId})"
	style:-webkit-backdrop-filter="url(#{filterId})"
>
	{@render children?.()}
</div>

<style>
	.lg2-element {
		position: relative;
		background: var(--lg2-bg-base, rgba(255, 255, 255, 0.05));
		border: 1px solid var(--lg2-border, rgba(255, 255, 255, 0.1));
		box-shadow:
			var(--lg2-shadow-sm, 0 8px 32px rgba(0, 0, 0, 0.1)),
			inset 0 1px 0 var(--lg2-highlight, rgba(255, 255, 255, 0.1));
	}
</style>
