<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		variant?: 'outline' | 'solid'
		class?: string
		color?: string
		strokeWidth?: string | number
	}

	let {
		variant = 'outline',
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.5',
		...rest
	}: IconProps = $props()
</script>

<!-- one drawing, two weights: the solid fills the same silhouette the outline strokes,
     so band and earcups keep an identical footprint across variants (F32 formula). -->
<svg
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 24 24"
	fill={variant === 'solid' ? color : 'none'}
	stroke={color}
	stroke-width={strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
	class={className}
	{...rest}
>
	<path
		fill-rule="evenodd"
		d="M12 3.833a8.167 8.167 0 0 0-8.167 8.167v1.365c0.365-0.128 0.758-0.198 1.167-0.198h2.333a1.167 1.167 0 0 1 1.167 1.167v7a1.167 1.167 0 0 1-1.167 1.167H5a3.5 3.5 0 0 1-3.5-3.5v-7a10.5 10.5 0 0 1 21 0v7a3.5 3.5 0 0 1-3.5 3.5h-2.333a1.167 1.167 0 0 1-1.167-1.167v-7a1.167 1.167 0 0 1 1.167-1.167h2.333c0.408 0 0.802 0.07 1.167 0.198V12a8.167 8.167 0 0 0-8.167-8.167Z"
		clip-rule="evenodd"
	/>
</svg>
