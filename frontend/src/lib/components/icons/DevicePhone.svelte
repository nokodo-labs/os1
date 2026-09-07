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
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	stroke-width={strokeWidth}
	fill="none"
	stroke={color}
	viewBox="0 0 24 24"
	{...rest}
>
	<path
		d="M7.273 2.25h9.455A1.477 1.477 0 0 1 18.205 3.727v16.545A1.477 1.477 0 0 1 16.727 21.75H7.273A1.477 1.477 0 0 1 5.795 20.273V3.727A1.477 1.477 0 0 1 7.273 2.25Z"
		stroke-linejoin="round"
	/>
	<path d="M10.227 18.795h3.545" stroke-linecap="round" />
</svg>
