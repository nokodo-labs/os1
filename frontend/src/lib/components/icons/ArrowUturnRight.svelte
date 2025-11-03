<script lang="ts">
	const { className = 'size-4', strokeWidth = '1.5' } = $props();
	</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke="currentColor"
	class={className}
>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="m15 15 6-6m0 0-6-6m6 6H9a6 6 0 0 0 0 12h3"
	/>
</svg>
