<script lang="ts">
	import { browser } from '$app/environment'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import User from '$lib/components/icons/User.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { resourceAccentStyle, resourceVisual } from '$lib/resources/resourceVisuals'
	import { files } from '$lib/stores/files.svelte'
	import { describeFileType, formatFileSize } from '$lib/utils/fileTypes'
	import { resourceSharing } from '$lib/utils/resourceSharing.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onclick?: () => void
	}

	let { resource, layout = 'grid', class: className = '', onclick }: Props = $props()
	let rootEl = $state<HTMLElement | null>(null)
	let shouldLoadPreview = $state(false)

	const mimeType = $derived((resource.meta?.mime_type as string) ?? '')
	const fileType = $derived(
		(resource.meta?.file_type as string) || describeFileType(mimeType, resource.title)
	)
	const fileSize = $derived((resource.meta?.file_size as number) ?? 0)
	const fileSizeLabel = $derived(formatFileSize(fileSize))
	const category = $derived((resource.meta?.category as string) ?? 'file')
	const source = $derived((resource.meta?.source as string) ?? '')
	const sharing = resourceSharing(() => resource)
	const authorMeta = $derived(sharing.authorMeta)
	const thumbnailUrl = $derived(files.getThumbnailUrl(resource.id) ?? null)
	const fileVisual = resourceVisual('file')
	const fileAccentStyle = resourceAccentStyle('file')

	const hasRenderedPreview = $derived(Boolean(thumbnailUrl && category === 'image'))

	$effect(() => {
		if (!browser || category !== 'image' || !rootEl) return
		const observer = new IntersectionObserver(
			(entries) => {
				if (!entries[0]?.isIntersecting) return
				shouldLoadPreview = true
				observer.disconnect()
			},
			{ rootMargin: '320px' }
		)
		observer.observe(rootEl)
		return () => observer.disconnect()
	})

	$effect(() => {
		if (shouldLoadPreview && category === 'image') void files.loadThumbnail(resource.id)
	})
</script>

{#snippet fileIcon()}
	<MimeIcon {mimeType} class="size-5" />
{/snippet}

{#snippet previewIcon()}
	<MimeIcon {mimeType} class="size-6" />
{/snippet}

{#snippet filePreview()}
	<ResourcePreview
		tone={fileVisual.tone}
		label={fileType}
		caption={source || (fileSize > 0 ? fileSizeLabel : 'file')}
		showFallback={!hasRenderedPreview}
		class="-mx-6 -mt-6"
	>
		{#snippet icon()}
			{@render previewIcon()}
		{/snippet}
		{#if thumbnailUrl && category === 'image'}
			<img
				src={thumbnailUrl}
				alt={resource.title}
				class="h-full w-full object-cover"
				draggable="false"
			/>
		{/if}
	</ResourcePreview>
{/snippet}

{#snippet content()}
	{#if layout === 'grid'}
		{@render filePreview()}
		<div class="mb-4 flex min-w-0 items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={fileAccentStyle}
			>
				{@render fileIcon()}
			</div>
			<div class="flex min-w-0 flex-col">
				<span class="text-foreground/60 truncate text-[13px] font-medium">{fileType}</span>
				{#if source}
					<span class="text-foreground/35 truncate text-[11px]">{source}</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled file'}
		</h3>
		{#if fileSize > 0}
			<p class="text-foreground/50 mb-3 truncate text-sm">{fileSizeLabel}</p>
		{/if}
		<div class="mt-auto flex min-w-0 items-center gap-2">
			<div class="text-foreground/50 flex min-w-0 items-center gap-2 text-xs">
				{#if authorMeta}
					<span class="flex min-w-0 items-center gap-1">
						<User class="size-3.5 shrink-0" />
						<span class="truncate">{authorMeta}</span>
					</span>
				{/if}
			</div>
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/45"
			/>
		</div>
	{:else}
		{#if thumbnailUrl && category === 'image'}
			<img
				src={thumbnailUrl}
				alt={resource.title}
				class="size-10 shrink-0 rounded-xl object-cover"
				draggable="false"
			/>
		{:else}
			<div
				class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[color-mix(in_oklch,var(--resource-accent)_15%,transparent)] text-(--accent-primary)"
				style={fileAccentStyle}
			>
				{@render fileIcon()}
			</div>
		{/if}
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled file'}
			</h3>
			<div class="flex min-w-0 items-center gap-2">
				{#if fileSize > 0}
					<span class="text-foreground/50 shrink-0 text-sm">{fileSizeLabel}</span>
				{/if}
				<span class="text-foreground/60 min-w-0 truncate text-sm">
					{fileType}
				</span>
				{#if authorMeta}
					<span class="text-foreground/50 flex min-w-0 items-center gap-1 text-xs">
						<User class="size-3.5 shrink-0" />
						<span class="truncate">{authorMeta}</span>
					</span>
				{/if}
				{#if source}
					<span class="text-foreground/45 shrink-0 text-xs">{source}</span>
				{/if}
			</div>
		</div>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
{/snippet}

{#if onclick}
	<button
		type="button"
		bind:this={rootEl}
		class="group liquid-glass liquid-glass--frosted w-full overflow-hidden rounded-2xl text-left transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
		'list'
			? 'flex cursor-pointer items-center gap-4 border-none bg-transparent px-5 py-4 text-inherit'
			: 'flex h-80 cursor-pointer flex-col border-none bg-transparent p-6 text-inherit'} {className}"
		{onclick}
	>
		{@render content()}
	</button>
{:else}
	<div
		bind:this={rootEl}
		class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 {layout ===
		'list'
			? 'flex items-center gap-4 px-5 py-4'
			: 'flex h-80 flex-col p-6'} {className}"
	>
		{@render content()}
	</div>
{/if}
