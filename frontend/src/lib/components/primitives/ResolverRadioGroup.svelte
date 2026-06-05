<script lang="ts">
	import { preferences } from '$lib/stores/preferences.svelte'
	import type { Component } from 'svelte'
	import CssRadioGroup from './CssRadioGroup.svelte'
	import LGRadioGroup from './liquid-glass/RadioGroup.svelte'

	type Option<T extends string> = {
		value: T
		label: string
		icon?: Component
		selectedClass?: string
		selectedIconClass?: string
	}

	interface RadioGroupProps<T extends string> {
		options: readonly Option<T>[]
		value: T
		onchange: (value: T) => void
		clearValue?: T
		class?: string
	}

	let {
		options,
		value,
		onchange,
		clearValue,
		class: className = '',
	}: RadioGroupProps<string> = $props()
</script>

{#if preferences.useSvgLiquidGlass}
	<LGRadioGroup {options} {value} {onchange} {clearValue} class={className} />
{:else}
	<CssRadioGroup {options} {value} {onchange} {clearValue} class={className} />
{/if}
