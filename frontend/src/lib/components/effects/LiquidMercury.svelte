<script lang="ts">
	import LiquidMercuryFilter from '$lib/liquid-mercury/b/LiquidMercuryFilter.svelte'
	import type { SurfaceFunction } from '$lib/liquid-mercury/b/physics'
	import { preferences } from '$lib/stores/preferences.svelte'
	import type { Snippet } from 'svelte'

	interface Props {
		tag?: string
		class?: string
		style?: string
		cornerRadius?: number
		surfaceFn?: SurfaceFunction
		bezelWidth?: number
		thickness?: number
		refractionStrength?: number
		mirrorDepth?: number
		specularOpacity?: number
		specularAngle?: number
		specularFalloff?: number
		children: Snippet
		[key: string]: unknown
	}

	let {
		tag = 'div',
		class: className = '',
		style: userStyle = '',
		cornerRadius,
		surfaceFn,
		bezelWidth,
		thickness,
		refractionStrength,
		mirrorDepth,
		specularOpacity,
		specularAngle,
		specularFalloff,
		children,
		...rest
	}: Props = $props()

	let el = $state<HTMLElement | null>(null)
	let width = $state(0)
	let height = $state(0)

	const filterId = `lm-${Math.random().toString(36).slice(2, 8)}`
	const useFilter = $derived(preferences.useSvgLiquidGlass && width > 0 && height > 0)

	const combinedStyle = $derived.by(() => {
		const parts: string[] = []
		if (userStyle) parts.push(userStyle)
		if (useFilter) {
			parts.push(`filter: url(#${filterId})`)
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
	<LiquidMercuryFilter
		{filterId}
		{width}
		{height}
		{cornerRadius}
		{surfaceFn}
		{bezelWidth}
		{thickness}
		{refractionStrength}
		{mirrorDepth}
		{specularOpacity}
		{specularAngle}
		{specularFalloff}
	/>
{/if}

<svelte:element
	this={tag}
	bind:this={el}
	class="liquid-mercury {className}"
	style={combinedStyle}
	{...rest}
>
	{@render children()}
</svelte:element>
