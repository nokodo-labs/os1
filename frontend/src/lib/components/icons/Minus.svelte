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

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	aria-hidden="true"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
>
	<path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14" />
</svg>
