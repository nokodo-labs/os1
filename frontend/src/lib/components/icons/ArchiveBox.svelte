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
		strokeWidth = '2.5',
		variant = 'outline',
		...rest
	}: IconProps = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill={variant === 'solid' ? color : 'none'}
	viewBox="0 0 24 24"
	stroke-width={variant === 'solid' ? undefined : strokeWidth}
	stroke={variant === 'solid' ? 'none' : color}
	aria-hidden="true"
	class={className}
	{...rest}
>
	{#if variant === 'solid'}
		<path
			d="M3.375 3A1.875 1.875 0 0 0 1.5 4.875v.75C1.5 6.66 2.34 7.5 3.375 7.5h17.25A1.875 1.875 0 0 0 22.5 5.625v-.75A1.875 1.875 0 0 0 20.625 3H3.375Z"
		/>
		<path
			fill-rule="evenodd"
			clip-rule="evenodd"
			d="m4.875 9 .513 8.718A3.75 3.75 0 0 0 9.13 21h5.74a3.75 3.75 0 0 0 3.742-3.282L19.125 9H4.875Zm4.875 3a.75.75 0 0 1 .75-.75h3a.75.75 0 0 1 0 1.5h-3a.75.75 0 0 1-.75-.75Z"
		/>
	{:else}
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="m20.25 7.5-.625 10.632a2.25 2.25 0 0 1-2.247 2.118H6.622a2.25 2.25 0 0 1-2.247-2.118L3.75 7.5M10 11.25h4M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125Z"
		/>
	{/if}
</svg>
