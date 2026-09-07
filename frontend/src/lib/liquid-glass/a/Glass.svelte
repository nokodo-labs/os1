<script lang="ts">
	import type { Snippet } from 'svelte'
	import type { HTMLAttributes } from 'svelte/elements'
	import { liquidGlass } from './liquidglass'
	import type { GlassInput } from './types'

	interface Props extends HTMLAttributes<HTMLDivElement> {
		preset?: GlassInput
		children?: Snippet
	}

	let { preset = 'standard', children, ...rest }: Props = $props()
</script>

<div {@attach liquidGlass(preset)} {...rest}>
	{@render children?.()}
</div>
