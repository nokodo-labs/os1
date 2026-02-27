<script lang="ts">
	import Document from '$lib/components/icons/Document.svelte'
	import Label from '$lib/components/icons/Label.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const labels = $derived((resource.meta?.labels as string[]) ?? [])
	const wordCount = $derived((resource.meta?.word_count as number) ?? 0)

	function stripMarkdown(text: string): string {
		return text
			.replace(/#{1,6}\s/g, '')
			.replace(/[*_~`]/g, '')
			.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
			.replace(/\n+/g, ' ')
			.trim()
	}
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
				class="flex size-11 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400"
			>
				<Document variant="solid" class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-[13px] font-medium text-white/60">note</span>
				{#if wordCount > 0}
					<span class="text-[11px] text-white/40">{wordCount} words</span>
				{/if}
			</div>
		</div>
		<h3 class="mb-1.5 truncate text-xl font-semibold text-white">
			{resource.title || 'untitled note'}
		</h3>
		{#if resource.preview}
			<p class="mb-3 line-clamp-3 text-sm leading-relaxed text-white/70">
				{stripMarkdown(resource.preview)}
			</p>
		{:else}
			<p class="mb-3 text-sm text-white/40 italic">empty note</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if labels.length > 0}
				<div class="flex items-center gap-1 overflow-hidden">
					<Label class="size-3.5 shrink-0 text-white/45" />
					{#each labels.slice(0, 3) as label (label)}
						<span
							class="truncate rounded-full bg-white/8 px-2 py-0.5 text-[11px] font-medium text-white/50"
						>
							{label}
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
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400"
		>
			<Document variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-base font-semibold text-white">
				{resource.title || 'untitled note'}
			</h3>
			{#if resource.preview}
				<p class="truncate text-sm text-white/65">{stripMarkdown(resource.preview)}</p>
			{:else}
				<p class="truncate text-sm text-white/45 italic">empty note</p>
			{/if}
		</div>
		{#if labels.length > 0}
			<div class="flex shrink-0 gap-1">
				{#each labels.slice(0, 2) as label (label)}
					<span class="rounded-full bg-white/8 px-2 py-0.5 text-[11px] text-white/50">
						{label}
					</span>
				{/each}
			</div>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-white/45"
		/>
	{/if}
</a>
