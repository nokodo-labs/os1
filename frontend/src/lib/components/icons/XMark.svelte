<script lang="ts">
	const {
		className = 'size-3.5',
		strokeWidth = '2',
		children,
	}: { className?: string; strokeWidth?: string; children?: import('svelte').Snippet } = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	viewBox="0 0 20 20"
	fill="currentColor"
	aria-hidden="true"
	stroke-width={strokeWidth}
	class={className}
>
	{#if children}{@render children()}{/if}
	<path
		d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z"
	/>
</svg>
