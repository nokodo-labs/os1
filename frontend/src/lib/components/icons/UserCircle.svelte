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
		{...rest}
	>
		<path
			fill-rule="evenodd"
			d="M12 1.25a10.75 10.75 0 1 0 0 21.5 10.75 10.75 0 0 0 0-21.5ZM12 5.25a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5ZM4.851 17.87C4.851 17.87 6.5 15.5 12 15.5C17.5 15.5 19.149 17.87 19.149 17.87A9.25 9.25 0 0 1 12 21.25A9.25 9.25 0 0 1 4.851 17.87Z"
			clip-rule="evenodd"
		/>
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
			d="M12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M4.271 18.3457C4.271 18.3457 6.50002 15.5 12 15.5C17.5 15.5 19.7291 18.3457 19.7291 18.3457"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M12 12C13.6569 12 15 10.6569 15 9C15 7.34315 13.6569 6 12 6C10.3431 6 9 7.34315 9 9C9 10.6569 10.3431 12 12 12Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
