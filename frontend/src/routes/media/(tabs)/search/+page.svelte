<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Search from '$lib/components/icons/Search.svelte'
</script>

<div class="flex flex-1 flex-col items-center justify-center">
	<EmptyState
		label="nothing to search yet"
		description="looking across movies and shows will land here once media is live."
	>
		{#snippet icon()}<Search variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
