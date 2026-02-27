<script lang="ts">
	import Brain from '$lib/components/icons/Brain.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
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
				class="flex size-10 items-center justify-center rounded-xl bg-teal-500/15 text-teal-400"
			>
				<Brain class="size-5" />
			</div>
			<span class="text-xs text-foreground/50">agent</span>
		</div>
		<h3 class="mb-1 truncate text-base font-medium text-foreground/90">
			{resource.title || 'untitled agent'}
		</h3>
		{#if resource.subtitle}
			<p class="mb-3 line-clamp-2 text-sm leading-relaxed text-foreground/60">
				{resource.subtitle}
			</p>
		{/if}
		<div class="mt-auto flex items-center gap-2">
			{#if toolCount > 0}
				<span class="text-xs text-foreground/40">{toolCount} tools</span>
			{/if}
			{#if author}
				<span class="text-xs text-foreground/40">by {author}</span>
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
			<h3 class="truncate text-base font-medium text-foreground/90">
				{resource.title || 'untitled agent'}
			</h3>
			{#if resource.subtitle}
				<p class="truncate text-sm text-foreground/60">{resource.subtitle}</p>
			{/if}
		</div>
		{#if toolCount > 0}
			<span class="shrink-0 text-xs text-foreground/40">{toolCount} tools</span>
		{/if}
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/40"
		/>
	{/if}
</a>
