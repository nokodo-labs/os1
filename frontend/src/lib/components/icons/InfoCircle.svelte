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
			d="M12 1.25a10.75 10.75 0 1 0 0 21.5 10.75 10.75 0 0 0 0-21.5ZM12.75 11.5a.75.75 0 0 0-1.5 0v5a.75.75 0 0 0 1.5 0v-5ZM12 6.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"
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
