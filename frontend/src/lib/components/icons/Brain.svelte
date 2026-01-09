<script lang="ts">
	const { className = 'w-4 h-4', strokeWidth = '1.5' } = $props()
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
		d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7Z"
	/>
	<path
		stroke-linecap="round"
		stroke-linejoin="round"
		d="M9 21h6M12 17v4M8.5 13c.83.95 2 1.5 3.5 1.5s2.67-.55 3.5-1.5"
	/>
</svg>
