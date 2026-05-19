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
		strokeWidth = '2',
		...rest
	}: IconProps = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	aria-hidden="true"
	class={className}
	{...rest}
>
	<path d="M2 8.5a15 15 0 0 1 20 0" stroke-linecap="round" stroke-linejoin="round" />
	<path d="M5 13a10 10 0 0 1 14 0" stroke-linecap="round" stroke-linejoin="round" />
	<path d="M8.5 16.5a5 5 0 0 1 7 0" stroke-linecap="round" stroke-linejoin="round" />
	<path d="M12 20h.01" stroke-linecap="round" stroke-linejoin="round" />
	<path d="m2 2 20 20" stroke-linecap="round" stroke-linejoin="round" />
</svg>
