<script lang="ts">
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const author = $derived((resource.meta?.author as string) ?? '')
</script>

<a
	href={resource.href}
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-5'} {className}"
>
	{#if layout === 'grid'}
		<div class="mb-3 flex items-center gap-2.5">
			<div
				class="flex size-10 items-center justify-center rounded-xl bg-fuchsia-500/15 text-fuchsia-400"
			>
				<Sparkles variant="solid" class="size-5" />
			</div>
			<span class="text-xs text-white/50">prompt</span>
		</div>
		<h3 class="mb-1 truncate text-base font-medium text-white/90">
			{resource.title || 'untitled prompt'}
		</h3>
		{#if resource.preview}
			<p class="mb-3 line-clamp-2 text-sm leading-relaxed text-white/60">
				{resource.preview}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if author}
				<span class="text-xs text-white/40">by {author}</span>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-white/40"
			/>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-fuchsia-500/15 text-fuchsia-400"
		>
			<Sparkles variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="truncate text-base font-medium text-white/90">
				{resource.title || 'untitled prompt'}
			</h3>
			{#if resource.preview}
				<p class="truncate text-sm text-white/60">{resource.preview}</p>
			{/if}
		</div>
		{#if author}
			<span class="shrink-0 text-xs text-white/40">by {author}</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-white/40"
		/>
	{/if}
</a>
