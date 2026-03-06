<script lang="ts">
	import type { Snippet } from 'svelte'
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		className?: string
		color?: string
		children?: Snippet
	}

	let {
		class: classProp,
		className,
		color = 'currentColor',
		children,
		...rest
	}: IconProps = $props()

	const computedClass = $derived.by(() => classProp ?? className ?? 'size-3.5')
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 20 20"
	fill={color}
	aria-hidden="true"
	class={computedClass}
	{...rest}
>
	{#if children}{@render children()}{/if}
	<path
		d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
	/>
</svg>
