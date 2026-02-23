<script lang="ts">
	import LiquidGlassFilter from '$lib/liquid-glass/b/LiquidGlassFilter.svelte'
	import type { SurfaceFunction } from '$lib/liquid-glass/b/physics'
	import { preferences } from '$lib/stores/preferences.svelte'
	import type { Snippet } from 'svelte'

	interface Props {
		/** html tag to render (default 'div') */
		tag?: string
		class?: string
		style?: string
		/** explicit corner radius for the SVG filter (defaults to pill shape) */
		cornerRadius?: number
		/** pass-through glass filter props */
		surfaceFn?: SurfaceFunction
		// filter customisation (forwarded to LiquidGlassFilter)
		blurRadius?: number
		specularOpacity?: number
		specularSaturation?: number
		specularAngle?: number
		specularFalloff?: number
		chromaticAberration?: number
		glassTint?: number
		bezelWidth?: number
		glassThickness?: number
		refractionStrength?: number
		component?: string
		children: Snippet
		[key: string]: unknown
	}

	let {
		tag = 'div',
		class: className = '',
		style: userStyle = '',
		cornerRadius,
		surfaceFn,
		blurRadius,
		specularOpacity,
		specularSaturation,
		specularAngle,
		specularFalloff,
		chromaticAberration,
		glassTint,
		bezelWidth,
		glassThickness,
		refractionStrength,
		component,
		children,
		...rest
	}: Props = $props()

	let el = $state<HTMLElement | null>(null)
	let width = $state(0)
	let height = $state(0)

	const filterId = `lg-${Math.random().toString(36).slice(2, 8)}`
	const useFilter = $derived.by(() => {
		const enabled =
			component === 'island'
				? preferences.useSvgLiquidGlassIsland || preferences.useSvgLiquidGlass
				: preferences.useSvgLiquidGlass
		return enabled && width > 0 && height > 0
	})

	const combinedStyle = $derived.by(() => {
		const parts: string[] = []
		if (userStyle) parts.push(userStyle)
		if (useFilter) {
			parts.push(`backdrop-filter: url(#${filterId})`)
			parts.push(`-webkit-backdrop-filter: url(#${filterId})`)
		}
		return parts.join('; ')
	})

	$effect(() => {
		const node = el
		if (!node) return
		const ro = new ResizeObserver((entries) => {
			for (const entry of entries) {
				if (entry.borderBoxSize?.length) {
					const box = entry.borderBoxSize[0]
					width = Math.round(box.inlineSize)
					height = Math.round(box.blockSize)
				} else {
					const rect = entry.contentRect
					width = Math.round(rect.width)
					height = Math.round(rect.height)
				}
			}
		})
		ro.observe(node, { box: 'border-box' })
		return () => ro.disconnect()
	})
</script>

{#if useFilter}
	<LiquidGlassFilter
		{filterId}
		{width}
		{height}
		{cornerRadius}
		{surfaceFn}
		{blurRadius}
		{specularOpacity}
		{specularSaturation}
		{specularAngle}
		{specularFalloff}
		{chromaticAberration}
		{glassTint}
		{bezelWidth}
		{glassThickness}
		{refractionStrength}
	/>
{/if}

<svelte:element
	this={tag}
	bind:this={el}
	class="liquid-glass {className}"
	style={combinedStyle}
	{...rest}
>
	{@render children()}
</svelte:element>
