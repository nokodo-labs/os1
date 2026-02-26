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
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
>
	<path stroke-linecap="round" stroke-linejoin="round" d="M3 8h13M3 12h10M3 16h7" />
	<line
		x1="1.5"
		y1="6"
		x2="1.5"
		y2="18"
		stroke={color}
		stroke-width="2.5"
		stroke-linecap="round"
	/>
</svg>
