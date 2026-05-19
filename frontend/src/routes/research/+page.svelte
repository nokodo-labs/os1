<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import Telescope from '$lib/components/icons/Telescope.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
</script>

<div
	class="flex min-h-full flex-1 flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<PageTitle icon={Telescope} label="research" iconColor="text-(--accent-primary)" />

	<EmptyState
		label="research"
		description="research workspace will live here soon."
		class="flex-1"
	>
		{#snippet icon()}<Telescope variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
