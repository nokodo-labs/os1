<script lang="ts">
	import { resolve } from '$app/paths'
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
	href={resolve(`/notes/${resource.id}`)}
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
				<span class="text-foreground/60 text-[13px] font-medium">note</span>
				{#if wordCount > 0}
					<span class="text-foreground/40 text-[11px]">{wordCount} words</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled note'}
		</h3>
		{#if resource.preview}
			<p class="text-foreground/70 mb-3 line-clamp-3 text-sm leading-relaxed">
				{stripMarkdown(resource.preview)}
			</p>
		{:else}
			<p class="text-foreground/40 mb-3 text-sm italic">empty note</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if labels.length > 0}
				<div class="flex items-center gap-1 overflow-hidden">
					<Label class="text-foreground/45 size-3.5 shrink-0" />
					{#each labels.slice(0, 3) as label (label)}
						<span
							class="bg-foreground/8 text-foreground/50 truncate rounded-full px-2 py-0.5 text-[11px] font-medium"
						>
							{label}
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
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-400"
		>
			<Document variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled note'}
			</h3>
			{#if resource.preview}
				<p class="text-foreground/65 truncate text-sm">{stripMarkdown(resource.preview)}</p>
			{:else}
				<p class="text-foreground/45 truncate text-sm italic">empty note</p>
			{/if}
		</div>
		{#if labels.length > 0}
			<div class="flex shrink-0 gap-1">
				{#each labels.slice(0, 2) as label (label)}
					<span
						class="bg-foreground/8 text-foreground/50 rounded-full px-2 py-0.5 text-[11px]"
					>
						{label}
					</span>
				{/each}
			</div>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
