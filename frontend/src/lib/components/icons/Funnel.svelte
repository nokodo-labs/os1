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
	stroke={variant === 'solid' ? 'none' : color}
	stroke-width={variant === 'solid' ? undefined : strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
	class={className}
	aria-hidden="true"
	{...rest}
>
	{#if variant === 'solid'}
		<path
			d="M4.1 4c-.72 0-1.1.85-.62 1.39L10 12.85V20a1 1 0 0 0 1.45.89l3-1.5a1 1 0 0 0 .55-.89v-5.65l6.52-7.46A.83.83 0 0 0 20.9 4H4.1z"
		/>
	{:else}
		<path d="M3 4h18l-7 8v7l-4 2v-9L3 4z" />
	{/if}
</svg>
