<script lang="ts">
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
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
</script>

<a
	href={resource.href}
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<div class="mb-4 flex items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400"
			>
				<ChatBubbles variant="solid" class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-[13px] font-medium text-white/60">chat</span>
				{#if messageCount > 0}
					<span class="text-[11px] text-white/40">{messageCount} messages</span>
				{/if}
			</div>
			{#if isArchived}
				<span
					class="ml-auto rounded-full bg-white/8 px-2.5 py-0.5 text-[11px] font-medium text-white/50"
				>
					archived
				</span>
			{/if}
		</div>
		<h3 class="mb-1.5 truncate text-xl font-semibold text-white">
			{resource.title || 'untitled chat'}
		</h3>
		{#if resource.preview}
			<p class="mb-3 line-clamp-2 text-sm leading-relaxed text-white/70">
				{resource.preview}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if tags.length > 0}
				<div class="flex gap-1 overflow-hidden">
					{#each tags.slice(0, 3) as tag (tag)}
						<span
							class="truncate rounded-full bg-white/8 px-2 py-0.5 text-[11px] font-medium text-white/50"
						>
							{tag}
						</span>
					{/each}
				</div>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-white/45"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-400"
		>
			<ChatBubbles variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-base font-semibold text-white">
				{resource.title || 'untitled chat'}
			</h3>
			{#if resource.preview}
				<p class="truncate text-sm text-white/65">{resource.preview}</p>
			{/if}
		</div>
		{#if messageCount > 0}
			<span class="shrink-0 text-xs text-white/45">{messageCount} msgs</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-white/45"
		/>
	{/if}
</a>
