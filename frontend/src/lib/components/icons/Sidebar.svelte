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
		stroke-width={strokeWidth}
		fill="none"
		stroke={color}
		viewBox="0 0 24 24"
		{...rest}
	>
		<path
			d="M3.75 9V15C3.75 17.8995 6.10051 20.25 9 20.25H9.25V3.75H9C6.10051 3.75 3.75 6.10051 3.75 9Z"
			fill={color}
			stroke="none"
		/>
		<rect x="3" y="3" width="18" height="18" rx="5" />
		<path d="M9.5 3V21" stroke-linecap="round" />
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
