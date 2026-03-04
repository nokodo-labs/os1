<script lang="ts">
	import { getApiOrigin } from '$lib/api/origin'
	import Document from '$lib/components/icons/Document.svelte'
	import Film from '$lib/components/icons/Film.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import SoundHigh from '$lib/components/icons/SoundHigh.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { fetchAuthenticatedBlob } from '$lib/stores/files.svelte'
	import type { ResourceItem } from './types'

	interface Props {
		resource: ResourceItem
		layout?: 'grid' | 'list'
		class?: string
	}

	let { resource, layout = 'grid', class: className = '' }: Props = $props()

	const fileType = $derived((resource.meta?.file_type as string) ?? 'file')
	const fileSize = $derived((resource.meta?.file_size as number) ?? 0)
	const mimeType = $derived((resource.meta?.mime_type as string) ?? '')
	const category = $derived((resource.meta?.category as string) ?? 'file')

	let thumbnailUrl = $state<string | null>(null)

	function formatFileSize(bytes: number): string {
		if (bytes === 0) return ''
		if (bytes < 1024) return `${bytes} B`
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
	}

	// load thumbnail for image files
	$effect(() => {
		if (category !== 'image') return
		let cancelled = false
		const url = `${getApiOrigin()}/v1/files/${resource.id}/content`
		void fetchAuthenticatedBlob(url)
			.then((blobUrl) => {
				if (!cancelled) thumbnailUrl = blobUrl
			})
			.catch(() => {})
		return () => {
			cancelled = true
			if (thumbnailUrl) {
				URL.revokeObjectURL(thumbnailUrl)
				thumbnailUrl = null
			}
		}
	})
</script>

{#snippet fileIcon()}
	{#if category === 'image'}
		<Photo class="size-5" />
	{:else if category === 'video'}
		<Film class="size-5" />
	{:else if category === 'audio'}
		<SoundHigh class="size-5" />
	{:else}
		<Document class="size-5" />
	{/if}
{/snippet}

<a
	href={resource.href}
	class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 hover:brightness-110 active:scale-[0.98] {layout ===
	'list'
		? 'flex items-center gap-4 px-5 py-4'
		: 'flex flex-col p-6'} {className}"
>
	{#if layout === 'grid'}
		{#if thumbnailUrl}
			<div class="-mx-6 -mt-6 mb-4 h-32 overflow-hidden">
				<img
					src={thumbnailUrl}
					alt={resource.title}
					class="h-full w-full object-cover"
					draggable="false"
				/>
			</div>
		{/if}
		<div class="mb-4 flex items-center gap-3" class:mt-0={thumbnailUrl}>
			<div
				class="flex size-11 items-center justify-center rounded-xl bg-rose-500/15 text-rose-400"
			>
				{@render fileIcon()}
			</div>
			<div class="flex flex-col">
				<span class="text-foreground/60 text-[13px] font-medium">{fileType}</span>
				{#if fileSize}
					<span class="text-foreground/40 text-[11px]">{formatFileSize(fileSize)}</span>
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
		{#if thumbnailUrl}
			<img
				src={thumbnailUrl}
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
				{#if fileSize}
					<span class="text-foreground/60 text-sm">{formatFileSize(fileSize)}</span>
				{/if}
				{#if mimeType}
					<span class="text-foreground/45 text-xs">{mimeType}</span>
				{/if}
			</div>
		</div>
		<Timestamp
			timestamp={new Date(resource.updatedAt)}
			mode="relative"
			className="shrink-0 text-xs text-foreground/45"
		/>
	{/if}
</a>
