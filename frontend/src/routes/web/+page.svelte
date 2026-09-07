<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
</script>

<div
	class="flex min-h-full flex-1 flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<PageTitle icon={GlobeAlt} label="web" iconColor="text-(--accent-primary)" />

	<EmptyState label="web" description="web workspace will live here soon." class="flex-1">
		{#snippet icon()}<GlobeAlt variant="solid" class="size-6" />{/snippet}
	</EmptyState>
</div>
