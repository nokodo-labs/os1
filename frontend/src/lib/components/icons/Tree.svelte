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
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	class={className}
	{...rest}
>
	<path
		d="M12 6.75V11M5.5 17.25V13a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v4.25"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
	<circle cx="12" cy="4.75" r="2" />
	<circle cx="5.5" cy="19.25" r="2" />
	<circle cx="18.5" cy="19.25" r="2" />
</svg>
