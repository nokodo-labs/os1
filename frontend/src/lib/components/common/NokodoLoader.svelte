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
</script>

<div
	class={`nokodo-loader ${className}`}
	data-expanded={expanded ? '1' : '0'}
	data-shimmer={shimmer ? '1' : '0'}
>
	<div class="nokodo-loader__solid">
		<span class="nokodo-loader__hidden">n</span><span class="nokodo-loader__visible">ok</span
		><span class="nokodo-loader__hidden">odo</span>
	</div>
	<div class="nokodo-loader__shimmer" aria-hidden="true">
		<span class="nokodo-loader__hidden">n</span><span class="nokodo-loader__visible">ok</span
		><span class="nokodo-loader__hidden">odo</span>
	</div>
</div>
