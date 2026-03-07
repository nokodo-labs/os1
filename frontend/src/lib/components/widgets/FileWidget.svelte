<script lang="ts">
	import { getApiOrigin } from '$lib/api/origin'
	import MimeIcon from '$lib/components/icons/MimeIcon.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import { fetchAuthenticatedBlob } from '$lib/stores/files.svelte'
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

	let thumbnailUrl = $state<string | null>(null)

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
	<MimeIcon {mimeType} class="size-5" />
{/snippet}

{#snippet content()}
	{#if layout === 'grid'}
		{#if thumbnailUrl}
			<div class="-mx-6 -mt-6 mb-4 h-32 overflow-hidden rounded-t-2xl">
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
			? 'flex items-center gap-4 px-5 py-4'
			: 'flex flex-col p-6'} {className}"
		{onclick}
	>
		{@render content()}
	</button>
{:else}
	<div
		class="group liquid-glass liquid-glass--frosted block overflow-hidden rounded-2xl transition-all duration-200 {layout ===
		'list'
			? 'flex items-center gap-4 px-5 py-4'
			: 'flex flex-col p-6'} {className}"
	>
		{@render content()}
	</div>
{/if}
