<script lang="ts">
	import { getApiBaseUrl } from '$lib/api/client'
	import type { FileContentPart, MediaContentPart } from '$lib/chat/types'
	import ImageLightbox from '$lib/components/chat/ImageLightbox.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Film from '$lib/components/icons/Film.svelte'
	import Headphone from '$lib/components/icons/Headphone.svelte'
	import { fetchAuthenticatedBlob } from '$lib/stores/files.svelte'
	import { onDestroy } from 'svelte'

	interface Props {
		mediaParts?: MediaContentPart[]
		fileParts?: FileContentPart[]
	}

	let { mediaParts = [], fileParts = [] }: Props = $props()

	const images = $derived(mediaParts.filter((p) => p.type === 'image'))
	const audioFiles = $derived(mediaParts.filter((p) => p.type === 'audio'))
	const videoFiles = $derived(mediaParts.filter((p) => p.type === 'video'))

	// grid columns: 1 image = full width, 2 = side by side, 3+ = 2-col grid
	const imageGridClass = $derived(
		images.length === 1 ? 'grid-cols-1' : images.length === 2 ? 'grid-cols-2' : 'grid-cols-2'
	)

	// lightbox state
	let lightboxOpen = $state(false)
	let lightboxSrc = $state('')
	let lightboxAlt = $state('')

	function openLightbox(src: string, alt: string) {
		lightboxSrc = src
		lightboxAlt = alt
		lightboxOpen = true
	}

	// authenticated blob URLs for media that needs auth
	let blobUrls = $state<Map<string, string>>(new Map())

	function resolveMediaUrl(part: MediaContentPart): string | undefined {
		// if we already have a blob URL, use it
		const cached = blobUrls.get(part.url)
		if (cached) return cached
		// if URL is already a blob/data URL, use directly
		if (part.url.startsWith('blob:') || part.url.startsWith('data:')) return part.url
		// otherwise start fetching and return undefined until ready
		fetchAuthenticatedBlob(part.url)
			.then((blobUrl) => {
				blobUrls = new Map(blobUrls).set(part.url, blobUrl)
			})
			.catch(() => {
				// fallback: try the raw URL (might work with cookies)
				blobUrls = new Map(blobUrls).set(part.url, part.url)
			})
		return undefined
	}

	onDestroy(() => {
		for (const url of blobUrls.values()) {
			if (url.startsWith('blob:')) URL.revokeObjectURL(url)
		}
	})
</script>

{#if images.length > 0}
	<div class="grid {imageGridClass} gap-1 overflow-hidden rounded-xl">
		{#each images as img, idx (idx)}
			{@const resolvedUrl = resolveMediaUrl(img)}
			{#if resolvedUrl}
				<button
					type="button"
					class="media-image-link block cursor-pointer overflow-hidden"
					class:col-span-2={images.length === 3 && idx === 0}
					onclick={() => openLightbox(resolvedUrl, img.filename ?? 'image attachment')}
					aria-label="view {img.filename ?? 'image'} fullscreen"
				>
					<img
						src={resolvedUrl}
						alt={img.filename ?? 'image attachment'}
						class="h-full max-h-72 w-full object-cover transition-transform duration-200 hover:scale-[1.02]"
						loading="lazy"
					/>
				</button>
			{:else}
				<!-- loading placeholder while auth fetch resolves -->
				<div
					class="bg-foreground/8 flex max-h-72 items-center justify-center rounded-xl"
					class:col-span-2={images.length === 3 && idx === 0}
					style="aspect-ratio: 4/3;"
				>
					<div class="bg-foreground/20 h-6 w-6 animate-pulse rounded-full"></div>
				</div>
			{/if}
		{/each}
	</div>
{/if}

{#if videoFiles.length > 0}
	<div class="space-y-2">
		{#each videoFiles as video, idx (idx)}
			{@const resolvedUrl = resolveMediaUrl(video)}
			<div class="overflow-hidden rounded-xl">
				{#if resolvedUrl}
					<video
						src={resolvedUrl}
						controls
						preload="metadata"
						class="max-h-80 w-full rounded-xl"
					>
						<track kind="captions" />
					</video>
				{:else}
					<div class="bg-foreground/8 flex h-48 items-center justify-center rounded-xl">
						<div class="bg-foreground/20 h-6 w-6 animate-pulse rounded-full"></div>
					</div>
				{/if}
				{#if video.filename}
					<div class="text-foreground/50 mt-1 flex items-center gap-1.5 truncate text-xs">
						<Film class="h-3.5 w-3.5 shrink-0" />
						{video.filename}
					</div>
				{/if}
			</div>
		{/each}
	</div>
{/if}

{#if audioFiles.length > 0}
	<div class="space-y-2">
		{#each audioFiles as audio, idx (idx)}
			{@const resolvedUrl = resolveMediaUrl(audio)}
			<div class="border-foreground/10 flex items-center gap-3 rounded-2xl border px-3 py-2">
				<Headphone class="text-foreground/45 h-4 w-4 shrink-0" />
				<audio
					src={resolvedUrl ?? ''}
					controls
					preload="metadata"
					class="h-8 w-full min-w-0"
				>
					<track kind="captions" />
				</audio>
				{#if audio.filename}
					<span class="text-foreground/50 shrink-0 truncate text-xs">
						{audio.filename}
					</span>
				{/if}
			</div>
		{/each}
	</div>
{/if}

{#if fileParts.length > 0}
	<div class="flex flex-wrap gap-1.5">
		{#each fileParts as file, idx (idx)}
			{@const downloadUrl =
				file.url ??
				(file.fileId ? `${getApiBaseUrl()}/v1/files/${file.fileId}/content` : null)}
			<div
				class="border-foreground/12 bg-foreground/6 flex items-center gap-2 rounded-xl border px-3 py-1.5"
			>
				<Document class="text-foreground/40 h-4 w-4 shrink-0" />
				{#if downloadUrl}
					<a
						href={downloadUrl}
						target="_blank"
						rel="noopener noreferrer"
						class="text-foreground/70 hover:text-foreground max-w-36 truncate text-xs font-medium transition-colors"
					>
						{file.filename ?? 'file'}
					</a>
				{:else}
					<span class="text-foreground/70 max-w-36 truncate text-xs font-medium">
						{file.filename ?? 'file'}
					</span>
				{/if}
				{#if file.mediaType}
					<span class="text-foreground/35 text-[10px]">
						{file.mediaType.split('/').pop()}
					</span>
				{/if}
			</div>
		{/each}
	</div>
{/if}

<ImageLightbox
	open={lightboxOpen}
	src={lightboxSrc}
	alt={lightboxAlt}
	onClose={() => (lightboxOpen = false)}
/>
