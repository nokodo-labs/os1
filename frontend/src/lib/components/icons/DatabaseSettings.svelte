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
	><path
		d="M3 5.5V11.5C3 11.5 3 14.5 10 14.5C17 14.5 17 11.5 17 11.5V5.5"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M10 2.5C17 2.5 17 5.5 17 5.5C17 5.5 17 8.5 10 8.5C3 8.5 3 5.5 3 5.5C3 5.5 3 2.5 10 2.5Z"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M10 20.5C3 20.5 3 17.5 3 17.5V11.5"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M18 20.5C19.105 20.5 20 19.605 20 18.5C20 17.395 19.105 16.5 18 16.5C17.636 16.5 17.294 16.597 17 16.768C16.402 17.113 16 17.76 16 18.5C16 19.24 16.402 19.887 17 20.232C17.294 20.403 17.636 20.5 18 20.5Z"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M18 21.5C19.657 21.5 21 20.157 21 18.5C21 16.843 19.657 15.5 18 15.5C16.343 15.5 15 16.843 15 18.5C15 20.157 16.343 21.5 18 21.5Z"
		stroke-linecap="round"
		stroke-linejoin="round"
		stroke-dasharray="0.3 2"
	></path></svg
>
