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
			d="M7.2 2.9a2.6 2.6 0 0 1 2.3-1.4c.62 0 1.2.22 1.65.58a2.6 2.6 0 0 1 1.7-.63c.98 0 1.83.54 2.27 1.34a2.85 2.85 0 0 1 3.63 2.74c0 .29-.043.57-.124.834.867.4 1.474 1.27 1.474 2.286 0 .69-.28 1.316-.733 1.77a.75.75 0 0 1-.53.22H4.71a.75.75 0 0 1-.53-.22 2.51 2.51 0 0 1-.733-1.77c0-1.07.673-1.982 1.617-2.34a2.85 2.85 0 0 1 2.136-3.424Z"
		/>
		<path
			fill-rule="evenodd"
			d="M4.4 12.15h15.2a.75.75 0 0 1 .74.87l-1.35 8.35a1.5 1.5 0 0 1-1.48 1.26H6.49a1.5 1.5 0 0 1-1.48-1.26L3.66 13.02a.75.75 0 0 1 .74-.87Zm4.24 1.5.55 7.48h1.5l-.55-7.48h-1.5Zm5.22 0-.55 7.48h1.5l.55-7.48h-1.5Z"
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
			d="M5.1 10.4a1.9 1.9 0 0 1-.36-3.73 2.25 2.25 0 0 1 2.1-3.06c.183 0 .361.022.532.063A2 2 0 0 1 9.5 2.25c.578 0 1.1.245 1.466.637a2 2 0 0 1 3.252.313 2.25 2.25 0 0 1 3.043 2.68c.86.245 1.489 1.036 1.489 1.974 0 .566-.229 1.078-.6 1.449M4.4 12.15h15.2l-1.35 8.35a.9.9 0 0 1-.888.75H6.638a.9.9 0 0 1-.888-.75L4.4 12.15Zm4.24 1.5.55 7.48m4.67-7.48-.55 7.48"
		/>
	</svg>
{/if}
