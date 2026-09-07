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
	<path d="M2.4 12L6.918 6.353H21.6V17.647H6.918L2.4 12Z" stroke={color} fill="none" />

	<!-- Tag hole -->
	<circle cx="9.176" cy="12" r="0.847" fill={color} stroke={color} />
</svg>
