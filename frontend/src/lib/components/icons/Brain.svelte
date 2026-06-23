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
		d="M12 5a3 3 0 1 0-6 .13 4 4 0 0 0-2.52 5.77 4 4 0 0 0 .55 6.58A4 4 0 1 0 12 18Z"
	/>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M12 5a3 3 0 1 1 6 .13 4 4 0 0 1 2.52 5.77 4 4 0 0 1-.55 6.58A4 4 0 1 1 12 18Z"
	/>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"
	/>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M17.6 6.5a3 3 0 0 0 .4-1.38M6 5.12a3 3 0 0 0 .4 1.38M3.48 10.9a4 4 0 0 1 .58-.4M19.94 10.5a4 4 0 0 1 .58.4M6 18a4 4 0 0 1-1.97-.52M19.97 17.48A4 4 0 0 1 18 18"
	/>
</svg>
