<script lang="ts">
	const { className = 'size-5', strokeWidth = '1.5' } = $props()
</script>

<svg
	class={className}
	aria-hidden="true"
	xmlns="http://www.w3.org/2000/svg"
	stroke-width={strokeWidth}
	fill="none"
	stroke="currentColor"
	viewBox="0 0 24 24"
>
	<path
		d="M3.75 9V15C3.75 17.8995 6.10051 20.25 9 20.25H9.25V3.75H9C6.10051 3.75 3.75 6.10051 3.75 9Z"
		fill="currentColor"
		stroke="none"
	/>
	<rect x="3" y="3" width="18" height="18" rx="5" />
	<path d="M9.5 3V21" stroke-linecap="round" />
</svg>
