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
		stroke={color}
		stroke-width={strokeWidth}
		width="24"
		height="24"
		viewBox="0 0 22 22"
		{...rest}
	>
		<path
			fill-rule="evenodd"
			stroke-linejoin="round"
			d="m2.125 11l8.875-8.875 8.875 8.875h-2.219v7.766a1.109 1.109 0 0 1-1.109 1.109H5.453a1.109 1.109 0 0 1-1.109-1.109v-7.766H2.125Zm6.656 8.875v-3.328a1.109 1.109 0 0 1 1.109-1.109h2.219a1.109 1.109 0 0 1 1.109 1.109v3.328h-4.437Z"
		/>
	</svg>
{:else}
	<svg
		stroke-width={strokeWidth}
		stroke={color}
		class={className}
		aria-hidden="true"
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		width="24"
		height="24"
		viewBox="0 0 22 22"
		{...rest}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="m2.125 11l8.875-8.875 8.875 8.875M4.344 9.336V18.766a1.109 1.109 0 0 0 1.109 1.109h3.328v-3.328a1.109 1.109 0 0 1 1.109-1.109h2.219a1.109 1.109 0 0 1 1.109 1.109v3.328h3.328a1.109 1.109 0 0 0 1.109-1.109v-9.43"
		/>
	</svg>
{/if}
