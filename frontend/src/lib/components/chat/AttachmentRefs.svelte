<script lang="ts">
	/**
	 * renders attachment resource refs ({type, id}) as previews.
	 *
	 * file refs are resolved to their metadata (mime type) so previewable media
	 * (image / audio / video) render inline with access to the file details
	 * modal, and other files render as a chip. non-file refs (note, thread,
	 * project, reminder, calendar event) render as resource widgets.
	 */

	import { getApiBaseUrl } from '$lib/api/client'
	import type { FileContentPart, MediaContentPart, ResourceAttachment } from '$lib/chat/types'
	import { getSourceConfig } from '$lib/citations/config'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import ResourceWidget from '$lib/components/widgets/ResourceWidget.svelte'
	import type { ResourceItem } from '$lib/components/widgets/types'
	import {
		apiFileToResource,
		files,
		type ApiFile,
		type FileResource,
	} from '$lib/stores/files.svelte'

	interface Props {
		refs: ResourceAttachment[]
		class?: string
	}

	let { refs, class: className = '' }: Props = $props()

	const apiBaseUrl = getApiBaseUrl()

	const fileRefs = $derived(refs.filter((ref) => ref.type === 'file'))
	const resourceRefs = $derived(refs.filter((ref) => ref.type !== 'file'))

	// ensure file metadata is loaded so previewable media can be categorized
	$effect(() => {
		for (const ref of fileRefs) void files.ensure(ref.id)
	})

	// resolved file resources, reactive over the files cache
	const resolvedFiles = $derived<FileResource[]>(
		fileRefs
			.map((ref) => files.all.find((file) => file.id === ref.id))
			.filter((file): file is ApiFile => file != null)
			.map(apiFileToResource)
	)

	function fileContentUrl(id: string): string {
		return `${apiBaseUrl}/v1/files/${id}/content`
	}

	function toMediaPart(file: FileResource): MediaContentPart | null {
		const category = file.meta.category
		if (category !== 'image' && category !== 'audio' && category !== 'video') return null
		return {
			type: category,
			url: fileContentUrl(file.id),
			filename: file.title,
			mediaType: file.meta.mime_type,
			fileId: file.id,
		}
	}

	function toFilePart(file: FileResource): FileContentPart | null {
		if (file.meta.category !== 'file') return null
		return {
			type: 'file',
			url: fileContentUrl(file.id),
			filename: file.title,
			mediaType: file.meta.mime_type,
			fileId: file.id,
		}
	}

	const mediaParts = $derived(
		resolvedFiles.map(toMediaPart).filter((part): part is MediaContentPart => part != null)
	)
	const fileParts = $derived(
		resolvedFiles.map(toFilePart).filter((part): part is FileContentPart => part != null)
	)

	function toResourceItem(ref: ResourceAttachment): ResourceItem {
		const cfg = getSourceConfig(ref.type)
		return {
			id: ref.id,
			type: cfg.resourceType,
			title: cfg.label,
			href: cfg.href(ref.id),
			updatedAt: Date.now(),
			createdAt: Date.now(),
		}
	}

	const resourceItems = $derived(resourceRefs.map(toResourceItem))
</script>

{#if mediaParts.length > 0 || fileParts.length > 0}
	<MediaAttachments {mediaParts} {fileParts} />
{/if}
{#if resourceItems.length > 0}
	<div class="flex flex-col gap-1.5 {className}">
		{#each resourceItems as item (`${item.type}:${item.id}`)}
			<ResourceWidget resource={item} layout="list" />
		{/each}
	</div>
{/if}
