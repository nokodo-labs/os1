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
		stroke={color}
		stroke-width={strokeWidth}
		viewBox="0 0 24 24"
		{...rest}
	>
		<circle cx="19" cy="5" r="3" fill={color} stroke="none" />
		<path
			d="M21 12V15C21 18.3137 18.3137 21 15 21H9C5.68629 21 3 18.3137 3 15V9C3 5.68629 5.68629 3 9 3H12"
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
			d="M19 8C20.6569 8 22 6.65685 22 5C22 3.34315 20.6569 2 19 2C17.3431 2 16 3.34315 16 5C16 6.65685 17.3431 8 19 8Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M21 12V15C21 18.3137 18.3137 21 15 21H9C5.68629 21 3 18.3137 3 15V9C3 5.68629 5.68629 3 9 3H12"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
