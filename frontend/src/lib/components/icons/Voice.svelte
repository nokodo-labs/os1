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
	><path d="M12 4L12 20" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M8 9L8 15"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M20 10L20 14" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M4 10L4 14"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path d="M16 7L16 17" stroke-linecap="round" stroke-linejoin="round"></path></svg
>
