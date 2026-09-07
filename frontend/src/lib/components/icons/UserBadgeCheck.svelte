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
	><path d="M2 19V18C2 14.134 5.134 11 9 11V11" stroke-linecap="round" stroke-linejoin="round"
	></path><path
		d="M15.804 11.314C16.446 10.609 17.554 10.609 18.196 11.314V11.314C18.521 11.67 18.987 11.863 19.468 11.84V11.84C20.42 11.796 21.204 12.58 21.16 13.532V13.532C21.137 14.013 21.33 14.479 21.687 14.804V14.804C22.391 15.446 22.391 16.554 21.687 17.196V17.196C21.33 17.521 21.137 17.987 21.16 18.468V18.468C21.204 19.42 20.42 20.204 19.468 20.16V20.16C18.987 20.137 18.521 20.33 18.196 20.687V20.687C17.554 21.391 16.446 21.391 15.804 20.687V20.687C15.479 20.33 15.013 20.137 14.532 20.16V20.16C13.58 20.204 12.796 19.42 12.84 18.468V18.468C12.863 17.987 12.67 17.521 12.314 17.196V17.196C11.609 16.554 11.609 15.446 12.314 14.804V14.804C12.67 14.479 12.863 14.013 12.84 13.532V13.532C12.796 12.58 13.58 11.796 14.532 11.84V11.84C15.013 11.863 15.479 11.67 15.804 11.314V11.314Z"
	></path><path
		d="M15.364 16L16.455 17.091L18.636 14.909"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path><path
		d="M9 11C11.209 11 13 9.209 13 7C13 4.791 11.209 3 9 3C6.791 3 5 4.791 5 7C5 9.209 6.791 11 9 11Z"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
