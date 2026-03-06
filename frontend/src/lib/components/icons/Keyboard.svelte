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
	fill="none"
	viewBox="0 0 24 24"
	stroke={color}
	stroke-width={strokeWidth}
	class={className}
	{...rest}
	><path
		d="M3 19V5C3 3.89543 3.89543 3 5 3H19C20.1046 3 21 3.89543 21 5V19C21 20.1046 20.1046 21 19 21H5C3.89543 21 3 20.1046 3 19Z"
	></path><path d="M8 14L12 10L16 14" stroke-linecap="round" stroke-linejoin="round"></path></svg
>
