<script lang="ts">
	import { preferences } from '$lib/stores/preferences.svelte'
	import CssSwitch from './CssSwitch.svelte'
	import LGSwitch from './liquid-glass/Switch.svelte'

	interface Props {
		checked?: boolean
		onchange?: (checked: boolean) => void
		disabled?: boolean
		id?: string
		ariaLabelledbyId?: string
		// LG-specific
		size?: 'sm' | 'md' | 'lg' | 'xl'
		forceActive?: boolean
		ariaLabel?: string
		glassThickness?: number
		bezelWidth?: number
		blur?: number
		specularOpacity?: number
		specularSaturation?: number
		// Standard-specific
		tooltip?: boolean | string
	}

	let {
		checked = $bindable(false),
		onchange,
		disabled = false,
		id = '',
		ariaLabelledbyId = '',
		// LG
		size = 'md',
		forceActive = false,
		ariaLabel = '',
		glassThickness,
		bezelWidth,
		blur,
		specularOpacity,
		specularSaturation,
		// standard
		tooltip = false,
	}: Props = $props()
</script>

{#if preferences.useSvgLiquidGlass}
	<LGSwitch
		bind:checked
		{onchange}
		{disabled}
		{id}
		{ariaLabelledbyId}
		{size}
		{forceActive}
		{ariaLabel}
		{glassThickness}
		{bezelWidth}
		{blur}
		{specularOpacity}
		{specularSaturation}
	/>
{:else}
	<CssSwitch
		bind:checked
		{onchange}
		{disabled}
		{id}
		{ariaLabelledbyId}
		{size}
		{forceActive}
		{ariaLabel}
		{glassThickness}
		{bezelWidth}
		{blur}
		{specularOpacity}
		{specularSaturation}
		{tooltip}
	/>
{/if}
