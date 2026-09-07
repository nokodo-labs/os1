<script lang="ts">
	import type { SVGAttributes } from 'svelte/elements'

	interface IconProps extends Omit<SVGAttributes<SVGSVGElement>, 'class'> {
		class?: string
		color?: string
		strokeWidth?: string | number
		variant?: 'outline' | 'solid'
	}

	let {
		class: className = 'size-4',
		color = 'currentColor',
		strokeWidth = '1.5',
		variant = 'outline',
		...rest
	}: IconProps = $props()
</script>

{#if variant === 'solid'}
	<!-- the outline's own bubble, grown to the footprint its 1.5 stroke paints, with the
	     check knocked out at the same 1.5 width the outline draws it -->
	<svg
		xmlns="http://www.w3.org/2000/svg"
		viewBox="0 0 24 24"
		fill={color}
		class={className}
		{...rest}
		><path
			fill-rule="evenodd"
			clip-rule="evenodd"
			d="M12 22.75C17.937 22.75 22.75 17.937 22.75 12C22.75 6.063 17.937 1.25 12 1.25C6.063 1.25 1.25 6.063 1.25 12C1.25 13.958 1.773 15.794 2.688 17.375L1.787 22.212L6.625 21.312C8.206 22.226 10.042 22.75 12 22.75ZM7.47 12.53L10.47 15.53a.75.75 0 0 0 1.06 0L16.53 10.53a.75.75 0 0 0-1.06-1.06L11 13.939 8.53 11.47a.75.75 0 0 0-1.06 1.06Z"
		></path></svg
	>
{:else}
	<svg
		xmlns="http://www.w3.org/2000/svg"
		fill="none"
		viewBox="0 0 24 24"
		stroke-width={strokeWidth}
		stroke={color}
		class={className}
		{...rest}
		><path d="M8 12L11 15L16 10" stroke-linecap="round" stroke-linejoin="round"></path><path
			d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 13.8214 2.48697 15.5291 3.33782 17L2.5 21.5L7 20.6622C8.47087 21.513 10.1786 22 12 22Z"
			stroke-linecap="round"
			stroke-linejoin="round"
		></path></svg
	>
{/if}
