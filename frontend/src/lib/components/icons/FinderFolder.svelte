<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	export type IconVariant = 'outline' | 'solid'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
		variant?: IconVariant
	}

	let {
		class: className = 'size-4',
		color = 'currentColor',
		variant = 'solid',
		...rest
	}: IconProps = $props()
</script>

<svg
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	viewBox="2 2 20 20"
	{...rest}
>
	{#if variant === 'outline'}
		<path
			d="M4.75 8.25h14.5c.69 0 1.25.56 1.25 1.25v8.75c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25V9.5c0-.69.56-1.25 1.25-1.25Z"
			fill="none"
			stroke={color}
			stroke-width="1.5"
			stroke-linejoin="round"
		/>
		<path
			d="M3.5 8.5V6.75c0-.69.56-1.25 1.25-1.25h5.1c.33 0 .65.13.88.37l1.16 1.16c.23.24.55.37.88.37h6.36c.69 0 1.25.56 1.25 1.25v.1"
			fill="none"
			stroke={color}
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	{:else}
		<!-- solid folder icon - back tab -->
		<path
			d="M4.6 7.2c0-.94.76-1.7 1.7-1.7h4.1c.45 0 .88.18 1.2.5l.95.95c.32.32.75.5 1.2.5h4.95c.94 0 1.7.76 1.7 1.7v.35H4.6V7.2Z"
			fill={color}
		/>
		<!-- solid folder icon - front body -->
		<path
			d="M4.6 9.1h14.8c.94 0 1.7.76 1.7 1.7v7c0 .94-.76 1.7-1.7 1.7H6.3c-.94 0-1.7-.76-1.7-1.7V9.1Z"
			fill={color}
		/>
	{/if}
</svg>
