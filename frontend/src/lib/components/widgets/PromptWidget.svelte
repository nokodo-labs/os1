<script lang="ts">
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
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
</script>

<div
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex min-h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview
			tone="sky"
			label="prompt"
			caption={author ? `by ${author}` : 'prompt'}
			class="-mx-6 -mt-6"
		>
			{#snippet icon()}
				<Sparkles variant="solid" class="size-6" />
			{/snippet}
			{#if resource.preview}
				<div
					class="bg-background/80 text-foreground/70 flex h-full w-full items-end overflow-hidden p-4 text-left text-sm leading-6"
				>
					<p class="line-clamp-4">{resource.preview}</p>
				</div>
			{/if}
		</ResourcePreview>
		<div class="mb-3 flex items-center gap-2.5">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-fuchsia-500/15 text-fuchsia-400"
			>
				<Sparkles variant="solid" class="size-5" />
			</div>
			<span class="text-foreground/50 text-xs">prompt</span>
		</div>
		<h3 class="text-foreground/90 mb-1 truncate text-base font-medium">
			{resource.title || 'untitled prompt'}
		</h3>
		{#if resource.preview}
			<p class="text-foreground/60 mb-3 line-clamp-2 text-sm leading-relaxed">
				{resource.preview}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
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
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-fuchsia-500/15 text-fuchsia-400"
		>
			<Sparkles variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground/90 truncate text-base font-medium">
				{resource.title || 'untitled prompt'}
			</h3>
			{#if resource.preview}
				<p class="text-foreground/60 truncate text-sm">{resource.preview}</p>
			{/if}
		</div>
		{#if author}
			<span class="text-foreground/40 shrink-0 text-xs">by {author}</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/40"
		/>
	{/if}
</div>
