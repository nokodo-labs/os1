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
	aria-hidden="true"
	{...rest}
	><path d="M13 16H18" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M6 8L10 12L6 16"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M2 18V6C2 4.89543 2.89543 4 4 4H20C21.1046 4 22 4.89543 22 6V18C22 19.1046 21.1046 20 20 20H4C2.89543 20 2 19.1046 2 18Z"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
