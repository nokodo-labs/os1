<script lang="ts">
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'

	let { className = '', label = 'loading more' } = $props<{
		className?: string
		label?: string
	}>()
</script>

<div class="flex items-center justify-center py-4 {className}" aria-label={label}>
	<NokodoLoader className="opacity-70" expanded={false} />
</div>
