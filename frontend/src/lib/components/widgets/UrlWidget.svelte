<script lang="ts">
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const domain = $derived.by(() => {
		try {
			return new URL(resource.href).hostname.replace(/^www\./, '')
		} catch {
			return resource.href
		}
	})
</script>

<a
	href={resource.href}
	target="_blank"
	rel="external noopener noreferrer"
	class="group liquid-glass liquid-glass--frosted block cursor-pointer overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex min-h-80 flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		<ResourcePreview tone="sky" label="web" caption={domain} class="-mx-6 -mt-6">
			{#snippet icon()}
				<GlobeAlt variant="solid" class="size-6" />
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
				class="flex size-10 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400"
			>
				<GlobeAlt variant="solid" class="size-5" />
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">web</span>
				<span class="text-foreground/40 text-[11px]">{domain}</span>
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled link'}
		</h3>
		{#if resource.preview}
			<p class="text-foreground/70 mb-3 line-clamp-3 text-sm leading-relaxed">
				{resource.preview}
			</p>
		{/if}
		<div class="mt-auto">
			<span class="text-foreground/45 truncate text-xs">{domain}</span>
		</div>
	{:else}
		<div
			class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400"
		>
			<GlobeAlt variant="solid" class="size-5" />
		</div>
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled link'}
			</h3>
			<p class="text-foreground/65 truncate text-sm">{domain}</p>
		</div>
	{/if}
</a>
