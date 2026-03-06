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
		<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
		<path
			fill-rule="evenodd"
			d="M1.323 11.447C2.811 6.976 7.028 3.75 12.001 3.75c4.97 0 9.185 3.223 10.675 7.69.12.362.12.752 0 1.113-1.487 4.471-5.705 7.697-10.677 7.697-4.97 0-9.186-3.223-10.675-7.69a1.762 1.762 0 0 1 0-1.113ZM17.25 12a5.25 5.25 0 1 1-10.5 0 5.25 5.25 0 0 1 10.5 0Z"
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
		aria-hidden="true"
		{...rest}
	>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z"
		/>
		<path
			stroke-linecap="round"
			stroke-linejoin="round"
			d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
		/>
	</svg>
{/if}
