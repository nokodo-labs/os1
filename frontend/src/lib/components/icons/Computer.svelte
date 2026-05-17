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
		d="M5 5.25h14A1.75 1.75 0 0 1 20.75 7v8A1.75 1.75 0 0 1 19 16.75H5A1.75 1.75 0 0 1 3.25 15V7A1.75 1.75 0 0 1 5 5.25Z"
		stroke-linejoin="round"
	/>
	<path d="M12 16.75v2.5" stroke-linecap="round" />
	<path d="M8.75 20.25h6.5" stroke-linecap="round" />
</svg>
