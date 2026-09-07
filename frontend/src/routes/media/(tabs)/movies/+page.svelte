<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Film from '$lib/components/icons/Film.svelte'
</script>

<div class="flex flex-1 flex-col items-center justify-center">
	<EmptyState
		label="no movies yet"
		description="your movies will show up here once media is live."
	>
		{#snippet icon()}<Film variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
