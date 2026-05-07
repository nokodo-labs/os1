<script lang="ts">
	import { getApiOrigin } from '$lib/api/origin'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { fetchAuthenticatedBlob } from '$lib/stores/files.svelte'
	import ResourcePreview from './ResourcePreview.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
		onclick?: () => void
	}

	let { resource, layout = 'grid', class: className = '', onclick }: Props = $props()

	const fileType = $derived((resource.meta?.file_type as string) ?? 'file')
	const mimeType = $derived((resource.meta?.mime_type as string) ?? '')
	const category = $derived((resource.meta?.category as string) ?? 'file')
	const source = $derived((resource.meta?.source as string) ?? '')
	const isPdf = $derived(mimeType.toLowerCase() === 'application/pdf')
	const canLoadBlobPreview = $derived(category === 'image' || category === 'video' || isPdf)
	const canLoadTextPreview = $derived(supportsTextPreview(mimeType))

	let previewUrl = $state<string | null>(null)
	let textPreview = $state<string | null>(null)

	$effect(() => {
		const fileId = resource.id
		const url = `${getApiOrigin()}/v1/files/${fileId}/content`
		let cancelled = false
		let loadedUrl: string | null = null

		previewUrl = null
		textPreview = null

		if (canLoadTextPreview) {
			void fetchAuthenticatedBlob(url)
				.then(async (blobUrl) => {
					try {
						const response = await fetch(blobUrl)
						const text = await response.text()
						if (!cancelled) textPreview = truncateText(text, 420)
					} finally {
						URL.revokeObjectURL(blobUrl)
					}
				})
				.catch(() => {})
			return () => {
				cancelled = true
			}
		}

		if (canLoadBlobPreview) {
			void fetchAuthenticatedBlob(url)
				.then((blobUrl) => {
					if (cancelled) {
						URL.revokeObjectURL(blobUrl)
						return
					}
					loadedUrl = blobUrl
					previewUrl = blobUrl
				})
				.catch(() => {})
		}

		return () => {
			cancelled = true
			if (loadedUrl) {
				URL.revokeObjectURL(loadedUrl)
			}
		}
	})

	function supportsTextPreview(value: string): boolean {
		const lower = value.toLowerCase()
		if (lower.startsWith('text/')) return true
		return (
			lower === 'application/json' ||
			lower === 'application/xml' ||
			lower === 'application/javascript' ||
			lower === 'application/yaml' ||
			lower === 'application/x-yaml' ||
			lower.endsWith('+json') ||
			lower.endsWith('+xml')
		)
	}

	function truncateText(value: string, maxLength: number): string {
		const normalized = value.replace(/\s+/g, ' ').trim()
		if (normalized.length <= maxLength) return normalized
		return `${normalized.slice(0, maxLength).trimEnd()}...`
	}
</script>

{#snippet fileIcon()}
	<MimeIcon {mimeType} class="size-5" />
{/snippet}

{#snippet previewIcon()}
	<MimeIcon {mimeType} class="size-6" />
{/snippet}

{#snippet filePreview()}
	<ResourcePreview
		tone="rose"
		label={fileType}
		caption={mimeType || source || 'file'}
		class="-mx-6 -mt-6"
	>
		{#snippet icon()}
			{@render previewIcon()}
		{/snippet}
		{#if previewUrl && category === 'image'}
			<img
				src={previewUrl}
				alt={resource.title}
				class="h-full w-full object-cover"
				draggable="false"
			/>
		{:else if previewUrl && category === 'video'}
			<video
				src={previewUrl}
				class="h-full w-full object-cover"
				preload="metadata"
				muted
				playsinline
			></video>
		{:else if previewUrl && isPdf}
			<iframe
				src={previewUrl}
				title={resource.title || 'pdf preview'}
				class="pointer-events-none h-full w-full border-0 bg-white"
				tabindex="-1"
			></iframe>
		{:else if textPreview}
			<div
				class="bg-background/85 text-foreground/75 h-full w-full overflow-hidden p-4 text-left text-[11px] leading-5"
			>
				{textPreview}
			</div>
		{/if}
	</ResourcePreview>
{/snippet}

{#snippet content()}
	{#if layout === 'grid'}
		{@render filePreview()}
		<div class="mb-4 flex items-center gap-3">
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400"
			>
				{@render fileIcon()}
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">{fileType}</span>
				{#if source}
					<span class="text-foreground/35 text-[11px]">{source}</span>
				{/if}
			</div>
		</div>
		<h3 class="text-foreground mb-1.5 truncate text-xl font-semibold">
			{resource.title || 'untitled file'}
		</h3>
		<div class="mt-auto flex items-center gap-2">
			{#if mimeType}
				<span class="text-foreground/50 text-xs">{mimeType}</span>
			{/if}
			<Timestamp
				timestamp={new Date(resource.updatedAt)}
				mode="relative"
				className="ml-auto shrink-0 text-xs text-foreground/45"
			/>
		</div>
	{:else}
		{#if previewUrl && category === 'image'}
			<img
				src={previewUrl}
				alt={resource.title}
				class="size-10 shrink-0 rounded-xl object-cover"
				draggable="false"
			/>
		{:else}
			<div
				class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400"
			>
				{@render fileIcon()}
			</div>
		{/if}
		<div class="min-w-0 flex-1">
			<h3 class="text-foreground truncate text-base font-semibold">
				{resource.title || 'untitled file'}
			</h3>
			<div class="flex items-center gap-2">
				<span class="text-foreground/60 text-sm">{fileType}</span>
				{#if source}
					<span class="text-foreground/45 text-xs">{source}</span>
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
		class="group liquid-glass liquid-glass--frosted w-full overflow-hidden rounded-2xl text-left transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
		'list'
			? 'flex cursor-pointer items-center gap-4 border-none bg-transparent px-5 py-4 text-inherit'
			: 'flex min-h-80 cursor-pointer flex-col border-none bg-transparent p-6 text-inherit'} {className}"
		{onclick}
	>
		{@render content()}
	</button>
{:else}
	<div
		class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 {layout ===
		'list'
			? 'flex items-center gap-4 px-5 py-4'
			: 'flex min-h-80 flex-col p-6'} {className}"
	>
		{@render content()}
	</div>
{/if}
