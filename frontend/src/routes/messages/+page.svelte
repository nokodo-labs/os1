<script lang="ts">
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import PageTitle from '$lib/components/PageTitle.svelte'
</script>

<div
	class="flex min-h-full flex-1 flex-col gap-6 pb-10"
	style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
>
	<PageTitle icon={ChatBubble} label="messages" iconColor="text-(--accent-primary)" />

	<section
		class="liquid-glass liquid-glass--frosted border-foreground/14 flex min-h-72 flex-1 items-center justify-center rounded-[18px] border px-6 py-10 text-center shadow-[inset_0_1px_0_rgb(255_255_255/0.12)]"
	>
		<div class="flex max-w-md flex-col items-center gap-3">
			<div
				class="border-foreground/12 bg-foreground/6 text-foreground/70 flex size-14 items-center justify-center rounded-2xl border"
			>
				<ChatBubble class="size-7" />
			</div>
			<div class="space-y-1">
				<h2 class="text-foreground text-lg font-semibold">messages</h2>
				<p class="text-foreground/55 text-sm">direct messages will live here soon.</p>
			</div>
		</div>
	</section>
</div>
