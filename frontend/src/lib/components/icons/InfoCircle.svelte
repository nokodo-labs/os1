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
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	stroke-width={variant === 'solid' ? undefined : strokeWidth}
	fill={variant === 'solid' ? color : 'none'}
	stroke={variant === 'solid' ? 'none' : color}
	viewBox="0 0 24 24"
	{...rest}
>
	{#if variant === 'solid'}
		<path
			fill-rule="evenodd"
			clip-rule="evenodd"
			d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12Zm8.706-1.442c1.146-.573 2.437.463 2.126 1.706l-.708 2.836.04-.02a.75.75 0 1 1 .672 1.34l-.041.021c-1.146.573-2.437-.463-2.126-1.706l.708-2.836-.04.02a.75.75 0 1 1-.672-1.34l.041-.021ZM12 9a.75.75 0 1 0 0-1.5A.75.75 0 0 0 12 9Z"
		/>
	{:else}
		<path d="M12 11.5V16.5" stroke-linecap="round" stroke-linejoin="round"></path><path
			d="M12 7.51L12.01 7.49889"
			stroke-linecap="round"
			stroke-linejoin="round"
		></path><path
			d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		></path>
	{/if}</svg
>
