<script lang="ts">
	import { preferences } from '$lib/stores/preferences.svelte'
	import CssSlider from './CssSlider.svelte'
	import LGSlider from './liquid-glass/Slider.svelte'

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

	let {
		size = 'md',
		min = 0,
		max = 100,
		step = 1,
		value = $bindable(50),
		onchange,
		disabled = false,
		forceActive = false,
		glassThickness,
		bezelWidth,
		refractiveIndex,
	}: Props = $props()
</script>

{#if preferences.useSvgLiquidGlass}
	<LGSlider
		{size}
		{min}
		{max}
		{step}
		bind:value
		{onchange}
		{disabled}
		{forceActive}
		{glassThickness}
		{bezelWidth}
		{refractiveIndex}
	/>
{:else}
	<CssSlider
		{size}
		{min}
		{max}
		{step}
		bind:value
		{onchange}
		{disabled}
		{forceActive}
		{glassThickness}
		{bezelWidth}
		{refractiveIndex}
	/>
{/if}
