<script lang="ts">
	const { className = 'w-4 h-4', strokeWidth = '1.5' } = $props()
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
	<circle cx="19" cy="5" r="3" fill="currentColor" stroke="none" />
	<path
		d="M21 12V15C21 18.3137 18.3137 21 15 21H9C5.68629 21 3 18.3137 3 15V9C3 5.68629 5.68629 3 9 3H12"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
</svg>
