<script lang="ts">
	import Brain from '$lib/components/icons/Brain.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const author = $derived((resource.meta?.author as string) ?? '')
	const toolCount = $derived((resource.meta?.tool_count as number) ?? 0)
</script>

<div
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex min-h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone="emerald"
			label="agent"
			caption={toolCount > 0 ? `${toolCount} tools` : author || 'agent'}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<Brain class="size-6" />
			{/snippet}
			{#if resource.subtitle}
				<div
					class="bg-background/80 text-foreground/70 flex h-full w-full items-end overflow-hidden p-4 text-left text-sm leading-6"
				>
					<p class="line-clamp-4">{resource.subtitle}</p>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-2.5">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-teal-500/15 text-teal-400"
			>
				<Brain class="size-5" />
			</div>
			<span class="text-foreground/50 text-xs">agent</span>
		</div>
		<h3 class="text-foreground/90 mb-1 truncate text-base font-medium">
			{resource.title || 'untitled agent'}
		</h3>
		{#if resource.subtitle}
			<p class="text-foreground/60 mb-3 line-clamp-2 text-sm leading-relaxed">
				{resource.subtitle}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if toolCount > 0}
				<span class="text-foreground/40 text-xs">{toolCount} tools</span>
			{/if}
			{#if author}
				<span class="text-foreground/40 text-xs">by {author}</span>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/40"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-teal-500/15 text-teal-400"
		>
			<Brain class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground/90 truncate text-base font-medium">
				{resource.title || 'untitled agent'}
			</h3>
			{#if resource.subtitle}
				<p class="text-foreground/60 truncate text-sm">{resource.subtitle}</p>
			{/if}
		</div>
		{#if toolCount > 0}
			<span class="text-foreground/40 shrink-0 text-xs">{toolCount} tools</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/40"
		/>
	{/if}
</div>
