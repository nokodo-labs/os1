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
		strokeWidth = '1.5',
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
	class={className}
	{...rest}
>
	{#if variant === 'solid'}
		<path
			fill-rule="evenodd"
			clip-rule="evenodd"
			d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm8.706-1.442c1.146-.573 2.437.463 2.126 1.706l-.708 2.836.04-.02a.75.75 0 1 1 .672 1.34l-.041.021c-1.146.573-2.437-.463-2.126-1.706l.708-2.836-.04.02a.75.75 0 1 1-.672-1.34l.041-.021ZM12 9a.75.75 0 1 0 0-1.5A.75.75 0 0 0 12 9Z"
		/>
	{:else}
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="m11.25 11.25.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"
		/>
	{/if}
</svg>
