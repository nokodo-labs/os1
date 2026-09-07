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

<!-- `ChatBubbleOval`'s angular twin: tight corners and a straight-cut tail, the
     shape whatsapp's border-trick tail draws. same bottom-left tail placement. -->
<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke={color}
	aria-hidden="true"
	class={className}
	{...rest}
>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M5.5 4h13A2.5 2.5 0 0 1 21 6.5v8a2.5 2.5 0 0 1-2.5 2.5H7l-4 3.5V6.5A2.5 2.5 0 0 1 5.5 4Z"
	/>
</svg>
