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
	stroke={color}
	fill="none"
	viewBox="0 0 24 24"
	{...rest}
	><path d="M12 6L12 12L18 12" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M21.8883 10.5C21.1645 5.68874 17.013 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C16.1006 22 19.6248 19.5318 21.1679 16"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M17 16H21.4C21.7314 16 22 16.2686 22 16.6V21"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
