<script lang="ts">
	import { resolve } from '$app/paths'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const tags = $derived((resource.meta?.tags as string[]) ?? [])
	const isArchived = $derived((resource.meta?.is_archived as boolean) ?? false)
	const messageCount = $derived((resource.meta?.message_count as number) ?? 0)
	const previewCaption = $derived(
		messageCount > 0
			? `${messageCount} messages`
			: tags.length > 0
				? tags.slice(0, 3).join(' - ')
				: 'chat'
	)
</script>

<a
	href={resolve(`/c/${resource.id}`)}
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex min-h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview tone="emerald" label="chat" caption={previewCaption} class="-mx-6 -mt-6">
			{#snippet icon()}
				<ChatBubbles variant="solid" class="size-6" />
			{/snippet}
			{#if resource.preview}
				<div
					class="bg-background/80 text-foreground/70 flex h-full w-full items-end overflow-hidden p-4 text-left text-sm leading-6"
				>
					<p class="line-clamp-4">{resource.preview}</p>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-3">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400"
			>
				<ChatBubbles variant="solid" class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">chat</span>
				{#if messageCount > 0}
					<span class="text-foreground/40 text-[11px]">{messageCount} messages</span>
				{/if}
			</div>
			{#if isArchived}
				<span
					class="bg-foreground/8 text-foreground/50 ml-auto rounded-full px-2.5 py-0.5 text-[11px] font-medium"
				>
					archived
				</span>
			{/if}
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled chat'}
		</h3>
		{#if resource.preview}
			<p class="text-foreground/70 mb-3 line-clamp-2 text-sm leading-relaxed">
				{resource.preview}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if tags.length > 0}
				<div class="flex gap-1 overflow-hidden">
					{#each tags.slice(0, 3) as tag (tag)}
						<span
							class="bg-foreground/8 text-foreground/50 truncate rounded-full px-2 py-0.5 text-[11px] font-medium"
						>
							{tag}
						</span>
					{/each}
				</div>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/45"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400"
		>
			<ChatBubbles variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled chat'}
			</h3>
			{#if resource.preview}
				<p class="text-foreground/65 truncate text-sm">{resource.preview}</p>
			{/if}
		</div>
		{#if messageCount > 0}
			<span class="text-foreground/45 shrink-0 text-xs">{messageCount} msgs</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
