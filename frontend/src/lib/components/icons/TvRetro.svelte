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
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<path
			d="M8.03 2.47a.75.75 0 0 0-1.06 1.06L10.19 6.75H12h1.81l3.22-3.22a.75.75 0 1 0-1.06-1.06L12 6.44 8.03 2.47Z"
		/>
		<path
			fill-rule="evenodd"
			d="M4.125 6.75C2.951 6.75 2 7.7 2 8.875v9C2 19.049 2.951 20 4.125 20h15.75C21.049 20 22 19.049 22 17.875v-9c0-1.174-.951-2.125-2.125-2.125H4.125Zm1.625 2.5A.75.75 0 0 0 5 10v6.75c0 .414.336.75.75.75h9a.75.75 0 0 0 .75-.75V10a.75.75 0 0 0-.75-.75h-9Zm12.5 1.5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Zm0 3.5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"
			clip-rule="evenodd"
		/>
	</svg>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		viewBox="0 0 24 24"
		stroke-width={strokeWidth}
		stroke={color}
		aria-hidden="true"
		class={className}
		{...rest}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="m7.5 3 4.5 4.5L16.5 3M4.125 7.5h15.75c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125H4.125A1.125 1.125 0 0 1 3 18.375v-9.75c0-.621.504-1.125 1.125-1.125Zm1.625 3h8.5v6.75h-8.5V10.5Zm12.375.375h.008v.008h-.008v-.008Zm0 3.25h.008v.008h-.008v-.008Z"
		/>
	</svg>
{/if}
