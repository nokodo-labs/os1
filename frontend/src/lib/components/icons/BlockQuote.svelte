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
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M4.716 6.759h17.034M4.716 12h13.103M4.716 17.241h9.172"
	/>
	<line
		x1="2.75"
		y1="4.138"
		x2="2.75"
		y2="19.862"
		stroke={color}
		stroke-width="2.5"
		stroke-linecap="round"
	/>
</svg>
