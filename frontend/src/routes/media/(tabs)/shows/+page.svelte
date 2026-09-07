<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import TvRetro from '$lib/components/icons/TvRetro.svelte'
</script>

<div class="flex flex-1 flex-col items-center justify-center">
	<EmptyState label="no shows yet" description="your shows will show up here once media is live.">
		{#snippet icon()}<TvRetro variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
