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
			fill-rule="evenodd"
			d="M2.25 2.25h19.5v19.5H2.25V2.25ZM17.5303 9.0303a.75.75 0 0 0-1.0606-1.0606L10 14.4393l-2.4697-2.4696a.75.75 0 0 0-1.0606 1.0606l3 3a.75.75 0 0 0 1.0606 0l7-7Z"
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
		class={className}
		{...rest}
	>
		<path
			d="M3 20.4V3.6C3 3.26863 3.26863 3 3.6 3H20.4C20.7314 3 21 3.26863 21 3.6V20.4C21 20.7314 20.7314 21 20.4 21H3.6C3.26863 21 3 20.7314 3 20.4Z"
			stroke-width="1.5"
		/>
		<path
			d="M7 12.5L10 15.5L17 8.5"
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
