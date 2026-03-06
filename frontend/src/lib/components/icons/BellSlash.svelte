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
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M9.143 17.082a24.248 24.248 0 0 0 3.844.148m-3.844-.148a23.856 23.856 0 0 1-5.455-1.31 8.964 8.964 0 0 0 2.3-5.542m3.155 6.852a3 3 0 0 0 5.667 1.97m1.965-2.277L21 21m-4.225-4.225a23.81 23.81 0 0 0 .51-3.427 5.989 5.989 0 0 0-2.010-4.577m-9.054 4.36A5.986 5.986 0 0 1 6 12c0-3.56 2.22-9 6-9a5.99 5.99 0 0 1 5.25 3.097M3 3l18 18"
	></path>
</svg>
