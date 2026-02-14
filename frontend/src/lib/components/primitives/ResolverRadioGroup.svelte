<script lang="ts">
	import { preferences } from '$lib/stores/preferences.svelte'
	import CssRadioGroup from './CssRadioGroup.svelte'
	import LGRadioGroup from './liquid-glass/RadioGroup.svelte'

	type Option<T extends string> = {
		value: T
		label: string
	}

	interface RadioGroupProps<T extends string> {
		options: readonly Option<T>[]
		value: T
		onchange: (value: T) => void
		class?: string
	}

	let { options, value, onchange, class: className = '' }: RadioGroupProps<string> = $props()
</script>

{#if preferences.useSvgLiquidGlass}
	<LGRadioGroup {options} {value} {onchange} class={className} />
{:else}
	<CssRadioGroup {options} {value} {onchange} class={className} />
{/if}
