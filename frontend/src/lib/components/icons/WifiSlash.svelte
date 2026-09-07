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
	<!-- heroicons 24/solid wifi weight: arcs pulled in 0.375 and stroked 2.25 span r-1.5..r+0.75 -->
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-linecap="round"
		stroke-linejoin="round"
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			stroke-width="2.25"
			d="M8.553 15.303A4.875 4.875 0 0 1 12.293 13.884M5.371 12.121A9.375 9.375 0 0 1 8.473 10.064M15.265 9.962A9.375 9.375 0 0 1 18.629 12.121M2.189 8.939A13.875 13.875 0 0 1 5.114 6.705M10.285 4.981A13.875 13.875 0 0 1 21.811 8.939M3 3 21 21"
		/>
		<path stroke-width="1.5" d="M12.53 18.22l-.53.53-.53-.53a.75.75 0 0 1 1.06 0Z" />
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill="none"
		stroke={color}
		stroke-width={strokeWidth}
		stroke-linecap="round"
		stroke-linejoin="round"
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			d="M8.288 15.038A5.25 5.25 0 0 1 12.459 13.52M5.106 11.856A9.75 9.75 0 0 1 8.565 9.625M13.334 9.092A9.75 9.75 0 0 1 18.894 11.856M1.924 8.674A14.25 14.25 0 0 1 5.178 6.239M9.051 4.808A14.25 14.25 0 0 1 22.076 8.674M12.53 18.22l-.53.53-.53-.53a.75.75 0 0 1 1.06 0ZM3 3 21 21"
		/>
	</svg>
{/if}
