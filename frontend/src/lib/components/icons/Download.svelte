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
		{...rest}
	>
		<path d="M5.25 21L18.75 21" fill="none" stroke-linecap="round" stroke-linejoin="round" />
		<path
			d="M11.156 3h1.687v9.562h3.094L12 16.5 8.063 12.563h3.094V3Z"
			stroke-linecap="round"
			stroke-linejoin="round"
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
		{...rest}
		><path d="M5.25 21L18.75 21" stroke-linecap="round" stroke-linejoin="round"></path><path
			d="M12 3V16.5M12 16.5L15.937 12.563M12 16.5L8.063 12.563"
			stroke-linecap="round"
			stroke-linejoin="round"
		></path></svg
	>
{/if}
