<script lang="ts">
	const { className = 'size-4', strokeWidth = '1.5' } = $props()
</script>

<svg
	xmlns="http://www.w3.org/2000/svg"
	fill="none"
	viewBox="0 0 24 24"
	stroke-width={strokeWidth}
	stroke="currentColor"
	class={className}
	><path d="M6 20L18 20" stroke-linecap="round" stroke-linejoin="round"></path><path
		d="M12 4V16M12 16L15.5 12.5M12 16L8.5 12.5"
		stroke-linecap="round"
		stroke-linejoin="round"
	></path></svg
>
