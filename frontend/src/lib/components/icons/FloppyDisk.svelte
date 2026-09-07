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
	stroke={color}
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	{...rest}
>
	<path
		stroke={color}
		stroke-linecap="round"
		stroke-width={strokeWidth}
		d="M10.781 16.875h2.437m8.174-11.326l-2.942-2.942A1.219 1.219 0 0 0 17.589 2.25H3.469a1.219 1.219 0 0 0-1.219 1.219v17.062a1.219 1.219 0 0 0 1.219 1.219h17.062a1.219 1.219 0 0 0 1.219-1.219V6.411a1.219 1.219 0 0 0-0.357-0.862ZM16.875 21.75v-7.312a1.219 1.219 0 0 0-1.219-1.219H8.344a1.219 1.219 0 0 0-1.219 1.219v7.312h9.75ZM8.344 2.25h7.312v3.656a1.219 1.219 0 0 1-1.219 1.219h-4.875a1.219 1.219 0 0 1-1.219-1.219V2.25Z"
	/>
</svg>
