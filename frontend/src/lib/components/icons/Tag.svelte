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
		strokeWidth = '1.8',
		...rest
	}: IconProps = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
>
	<!-- Tag body with pointed end -->
	<path d="M4 12 L8 7 H21 V17 H8 L4 12 Z" stroke={color} fill="none" />

	<!-- Tag hole -->
	<circle cx="10" cy="12" r="0.75" fill={color} stroke={color} />
</svg>
