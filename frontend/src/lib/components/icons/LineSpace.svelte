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
	><path d="M11 6H21" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M11 12H21"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M11 18H21" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M5 19V5M5 19L3 16.5M5 19L7 16.5M5 5L3 7M5 5L7 7"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
