<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
		strokeWidth?: string | number
	}

	let {
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.5',
		...rest
	}: IconProps = $props()
</script>

<svg
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	stroke-width={strokeWidth}
	fill="none"
	stroke={color}
	viewBox="0 0 24 24"
	{...rest}
	><path d="M10.138 3L5.793 7.345L10.138 11.69" stroke-linecap="round" stroke-linejoin="round"
	></path><path
		d="M5.793 7.345L13.241 7.345C15.984 7.345 18.207 9.568 18.207 12.31V21"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
