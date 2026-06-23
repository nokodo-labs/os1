<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
	}

	let { class: className = 'size-4', color = 'currentColor', ...rest }: IconProps = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 24 24"
	fill={color}
	class={className}
	aria-hidden="true"
	{...rest}
>
	<circle cx="9" cy="5" r="1.5" />
	<circle cx="15" cy="5" r="1.5" />
	<circle cx="9" cy="12" r="1.5" />
	<circle cx="15" cy="12" r="1.5" />
	<circle cx="9" cy="19" r="1.5" />
	<circle cx="15" cy="19" r="1.5" />
</svg>
