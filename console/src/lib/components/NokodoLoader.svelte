<script lang="ts">
	let {
		shimmer = true,
		expanded = true,
		className = '',
	} = $props<{
		shimmer?: boolean
		expanded?: boolean
		className?: string
	}>()

	const shimmerClass = $derived.by(() => (shimmer ? 'shimmer' : ''))
</script>

<div class={`nokodo-loader ${shimmerClass} ${className}`} data-expanded={expanded ? '1' : '0'}>
	<span class="nokodo-loader__hidden">n</span><span class="nokodo-loader__visible">ok</span><span
		class="nokodo-loader__hidden">odo</span
	>
</div>
