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

{#if variant === 'solid'}
	<svg
		class={className}
		aria-hidden="true"
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		viewBox="0 0 24 24"
		{...rest}
	>
		<!-- left panel fill (properly follows the rounded corners) -->
		<path d="M9.5 3H8A5 5 0 0 0 3 8V16A5 5 0 0 0 8 21H9.5V3Z" fill={color} />
		<!-- outer border -->
		<rect x="3" y="3" width="18" height="18" rx="5" stroke={color} stroke-width={strokeWidth} />
		<!-- divider -->
		<path d="M9.5 3V21" stroke={color} stroke-width={strokeWidth} stroke-linecap="round" />
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		viewBox="0 0 24 24"
		stroke-width={strokeWidth}
		stroke={color}
		class={className}
		{...rest}
	>
		<rect
			x="3"
			y="3"
			width="18"
			height="18"
			rx="5"
			ry="5"
			stroke-linecap="round"
			stroke-linejoin="round"
			fill="none"
		/>
		<path d="M9.5 21V3" stroke-linecap="round" stroke-linejoin="round" />
	</svg>
{/if}
