<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
</script>

<div class="flex flex-1 flex-col items-center justify-center">
	<EmptyState
		label="nothing to discover yet"
		description="picks and highlights will show up here once media is live."
	>
		{#snippet icon()}<Sparkles variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
