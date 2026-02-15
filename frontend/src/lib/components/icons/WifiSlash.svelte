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
	><path d="M2 2l20 20" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M8.5 16.5a5 5 0 0 1 7 0"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M2 8.82a15 15 0 0 1 4.17-2.65" stroke-linecap="round" stroke-linejoin="round"
	></path><path
		d="M10.66 5c4.01-.36 8.14.9 11.34 3.76"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M16.85 11.25a10 10 0 0 1 2.22 1.68"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M5 12.86a10 10 0 0 1 5.17-2.89" stroke-linecap="round" stroke-linejoin="round"
	></path><path d="M12 20h.01" stroke-linecap="round" stroke-linejoin="round"></path></svg
>
