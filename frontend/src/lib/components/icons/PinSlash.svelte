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
	><path d="M9.5 14.5L3 21" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M7.67602 7.8896L6.69713 7.78823L5.00007 9.48528L14.1925 18.6777L15.8895 16.9806L15.7879 16M11.4847 7L15.1568 2.67141L21.0065 8.5211L16.6991 12.175"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M3 3L21 21" stroke-linecap="round" stroke-linejoin="round"></path></svg
>
