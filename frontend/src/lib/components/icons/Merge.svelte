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
>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M7.125 7.125v9.75m0-9.75a2.437 2.437 0 1 0 0-4.875 2.437 2.437 0 0 0 0 4.875Zm0 9.75a2.437 2.437 0 1 0 0 4.875 2.437 2.437 0 0 0 0-4.875Zm7.312-2.437a2.437 2.437 0 1 1 4.875 0 2.437 2.437 0 0 1-4.875 0Zm0 0h-1.219a6.094 6.094 0 0 1-6.094-6.094v-0.609"
	/>
</svg>
