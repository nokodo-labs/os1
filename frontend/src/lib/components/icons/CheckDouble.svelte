<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
		strokeWidth?: string | number
	}

	let {
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.5',
		...rest
	}: IconProps = $props()
</script>

<!-- `Check`'s tick, twice: the trailing one is the same shape at the same angle,
     the leading one cut short where the other passes over it. -->
<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
>
	<path stroke-linecap="round" stroke-linejoin="round" d="m1.5 13.5 4.5 4.5 8.25-11" />
	<path stroke-linecap="round" stroke-linejoin="round" d="m9 13.5 4.5 4.5 9-12" />
</svg>
