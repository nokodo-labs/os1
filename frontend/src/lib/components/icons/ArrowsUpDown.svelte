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
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill={color}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<!-- up arrow -->
		<path
			d="M7 3a1 1 0 0 1 .8.4l3 4a1 1 0 0 1-1.6 1.2L8 7v7a1 1 0 1 1-2 0V7L4.8 8.6a1 1 0 1 1-1.6-1.2l3-4A1 1 0 0 1 7 3Z"
		/>
		<!-- down arrow -->
		<path
			d="M17 21a1 1 0 0 1-.8-.4l-3-4a1 1 0 0 1 1.6-1.2L16 17v-7a1 1 0 1 1 2 0v7l1.2-1.6a1 1 0 0 1 1.6 1.2l-3 4a1 1 0 0 1-.8.4Z"
		/>
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		viewBox="0 0 24 24"
		stroke-width={strokeWidth}
		stroke={color}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<!-- up arrow -->
		<path stroke-linecap="round" stroke-linejoin="round" d="M7 4v10m0-10 3 3m-3-3L4 7" />
		<!-- down arrow -->
		<path stroke-linecap="round" stroke-linejoin="round" d="M17 20V10m0 10-3-3m3 3 3-3" />
	</svg>
{/if}
