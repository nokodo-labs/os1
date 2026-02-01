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
	><path d="M10 3L6 21" stroke-linecap="round"></path><path
		d="M20.5 16H2.5"
		stroke-linecap="round"
	></path><path d="M22 7H4" stroke-linecap="round"></path><path
		d="M18 3L14 21"
		stroke-linecap="round"
	></path></svg
>
