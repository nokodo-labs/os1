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
		{...rest}
	>
		<path
			d="M18.309 2.25H2.938C2.558 2.25 2.25 2.558 2.25 2.938V18.309"
			fill="none"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<!-- front frame filled, with the ridge and sun knocked out -->
		<path
			fill-rule="evenodd"
			d="M21.75 6.379V21.062C21.75 21.442 21.442 21.75 21.062 21.75H6.379C5.999 21.75 5.691 21.442 5.691 21.062V6.379C5.691 5.999 5.999 5.691 6.379 5.691H21.062C21.442 5.691 21.75 5.999 21.75 6.379ZM5.691 16.932L11.936 14.868L21.75 18.309V21.062C21.75 21.442 21.442 21.75 21.062 21.75H6.379C5.999 21.75 5.691 21.442 5.691 21.062V16.932ZM16.588 8.272a2.581 2.581 0 1 0 0 5.162 2.581 2.581 0 0 0 0-5.162Z"
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
		aria-hidden="true"
		{...rest}
	>
		<path
			d="M21.75 6.379V21.062C21.75 21.442 21.442 21.75 21.062 21.75H6.379C5.999 21.75 5.691 21.442 5.691 21.062V6.379C5.691 5.999 5.999 5.691 6.379 5.691H21.062C21.442 5.691 21.75 5.999 21.75 6.379Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M18.309 2.25H2.938C2.558 2.25 2.25 2.558 2.25 2.938V18.309"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M5.691 16.932L11.936 14.868L21.75 18.309"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
		<path
			d="M16.588 12.574C15.638 12.574 14.868 11.803 14.868 10.853C14.868 9.903 15.638 9.132 16.588 9.132C17.538 9.132 18.309 9.903 18.309 10.853C18.309 11.803 17.538 12.574 16.588 12.574Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
