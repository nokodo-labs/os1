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
		fill={color}
		viewBox="0 0 24 24"
		{...rest}
	>
		<path
			d="M3.53 2.47a.75.75 0 0 0-1.06 1.06l18 18a.75.75 0 1 0 1.06-1.06l-18-18ZM20.57 16.476c-.223.082-.448.161-.674.238L7.319 4.137A6.75 6.75 0 0 1 18.75 9v.75c0 2.123.8 4.057 2.118 5.52a.75.75 0 0 1-.297 1.206Z"
		></path>
		<path
			fill-rule="evenodd"
			d="M5.25 9c0-.184.007-.366.021-.545l10.362 10.362a3.75 3.75 0 0 1-7.363-1.048 24.585 24.585 0 0 1-4.831-1.244.75.75 0 0 1-.298-1.205A8.217 8.217 0 0 0 5.25 9.75V9Zm4.502 8.9a2.25 2.25 0 1 0 4.496 0 25.057 25.057 0 0 1-4.496 0Z"
			clip-rule="evenodd"
		></path>
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
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M9.143 17.082a24.248 24.248 0 0 0 3.844.148m-3.844-.148a23.856 23.856 0 0 1-5.455-1.31 8.964 8.964 0 0 0 2.3-5.542m3.155 6.852a3 3 0 0 0 5.667 1.97m1.965-2.277L21 21m-4.225-4.225a23.81 23.81 0 0 0 3.536-1.003A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6.53 6.53m10.245 10.245L6.53 6.53M3 3l3.53 3.53"
		></path>
	</svg>
{/if}
