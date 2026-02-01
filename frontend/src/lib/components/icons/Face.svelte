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
		d="M12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2Z"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path>
	<path d="M16 8L16 10" stroke-linecap="round" stroke-linejoin="round"></path>

	<path d="M8 8L8 10" stroke-linecap="round" stroke-linejoin="round"></path>

	<path
		d="M9 16C9 16 10 17 12 17C14 17 15 16 15 16"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path>

	<path d="M12 8L12 13L11 13" stroke-linecap="round" stroke-linejoin="round"></path>
</svg>
