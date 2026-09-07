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
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			d="M16.875 12H18.581C18.985 12 19.312 12.327 19.312 12.731V21.019C19.312 21.423 18.985 21.75 18.581 21.75H5.419C5.015 21.75 4.688 21.423 4.688 21.019V12.731C4.688 12.327 5.015 12 5.419 12H7.125Z"
			stroke-linejoin="round"
		/>
		<path
			d="M16.875 12V7.125C16.875 5.5 15.9 2.25 12 2.25C8.1 2.25 7.125 5.5 7.125 7.125V12"
			fill="none"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{:else}
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
			d="M16.875 12H18.581C18.985 12 19.312 12.327 19.312 12.731V21.019C19.312 21.423 18.985 21.75 18.581 21.75H5.419C5.015 21.75 4.688 21.423 4.688 21.019V12.731C4.688 12.327 5.015 12 5.419 12H7.125M16.875 12V7.125C16.875 5.5 15.9 2.25 12 2.25C8.1 2.25 7.125 5.5 7.125 7.125V12M16.875 12H7.125"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
