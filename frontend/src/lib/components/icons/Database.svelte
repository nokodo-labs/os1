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
		stroke={color}
		stroke-width={strokeWidth}
		class={className}
		aria-hidden="true"
		{...rest}
	>
		<!-- cylinder silhouette with the two tier separators knocked out -->
		<path
			fill-rule="evenodd"
			d="M12 3C19 3 19 6 19 6V18C19 18 19 21 12 21C5 21 5 18 5 18V6C5 6 5 3 12 3ZM5 6C5 6 5 9 12 9C19 9 19 6 19 6V9C19 9 19 12 12 12C5 12 5 9 5 9V6ZM5 12C5 12 5 15 12 15C19 15 19 12 19 12V15C19 15 19 18 12 18C5 18 5 15 5 15V12Z"
			stroke-linejoin="round"
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
		<path d="M5 12V18C5 18 5 21 12 21C19 21 19 18 19 18V12" />
		<path d="M5 6V12C5 12 5 15 12 15C19 15 19 12 19 12V6" />
		<path d="M12 3C19 3 19 6 19 6C19 6 19 9 12 9C5 9 5 6 5 6C5 6 5 3 12 3Z" />
	</svg>
{/if}
