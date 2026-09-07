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
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	width="24"
	height="24"
	viewBox="0 0 22 22"
	{...rest}
	><path d="M8.5 13.5L2 20" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M6.676 6.89L5.697 6.788L4 8.485L13.193 17.678L14.89 15.981L14.788 15M10.485 6L14.157 1.671L20.007 7.521L15.699 11.175"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M2 2L20 20" stroke-linecap="round" stroke-linejoin="round"></path></svg
>
