<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
		strokeWidth?: string | number
		variant?: 'outline' | 'solid'
	}

	let {
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.7',
		variant = 'outline',
		...rest
	}: IconProps = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 24 24"
	fill={variant === 'solid' ? color : 'none'}
	stroke={color}
	stroke-width={strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
	class={className}
	aria-hidden="true"
	{...rest}
>
	<path d="M3 4h18l-7 8v7l-4 2v-9L3 4z" />
</svg>
