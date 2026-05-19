<script lang="ts">
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
</script>

<div
	class="flex min-h-full flex-1 flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<PageTitle icon={ChatBubble} label="messages" iconColor="text-(--accent-primary)" />

	<EmptyState label="messages" description="direct messages will live here soon." class="flex-1">
		{#snippet icon()}<ChatBubble class="size-6" />{/snippet}
	</EmptyState>
</div>
