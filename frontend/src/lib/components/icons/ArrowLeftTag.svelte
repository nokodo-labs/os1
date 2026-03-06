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
	><path
		d="M16.75 12H6.75M6.75 12L9.5 14.75M6.75 12L9.5 9.25"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M2 15V9C2 6.79086 3.79086 5 6 5H18C20.2091 5 22 6.79086 22 9V15C22 17.2091 20.2091 19 18 19H6C3.79086 19 2 17.2091 2 15Z"
	></path></svg
>
