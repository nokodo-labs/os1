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
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	fill={color}
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
	><path d="M12 2.25L12 21.75" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M7.125 8.344L7.125 15.656"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M21.75 9.563L21.75 14.438" stroke-linecap="round" stroke-linejoin="round"
	></path><path d="M2.25 9.563L2.25 14.438" stroke-linecap="round" stroke-linejoin="round"
	></path><path d="M16.875 5.906L16.875 18.094" stroke-linecap="round" stroke-linejoin="round"
	></path></svg
>
