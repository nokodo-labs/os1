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
	viewBox="0 0 24 24"
	fill={color}
	class={className}
	stroke-width={strokeWidth}
	{...rest}
>
	<rect x="6" y="6" width="12" height="12" rx="2" />
</svg>
