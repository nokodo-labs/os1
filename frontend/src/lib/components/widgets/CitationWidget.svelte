<script lang="ts">
	import type { components } from '$lib/api/types'
	import ChatWidget from './ChatWidget.svelte'
	import FileWidget from './FileWidget.svelte'
	import NoteWidget from './NoteWidget.svelte'
	import UrlWidget from './UrlWidget.svelte'
	import type { ResourceItem } from './types'

	type Citation = components['schemas']['Citation']

	interface Props {
		citation: Citation
		layout?: 'grid' | 'list'
		class?: string
	}

	let { citation, layout = 'grid', class: className = '' }: Props = $props()

	function citationUrl(c: Citation): string {
		switch (c.source_type) {
			case 'url':
				return c.source_id
			case 'file':
				return `/api/v1/files/${c.source_id}/content`
			case 'note':
				return `/notes/${c.source_id}`
			case 'thread':
				return `/c/${c.source_id}`
			default:
				return '#'
		}
	}

	const resource: ResourceItem = $derived({
		id: citation.source_id,
		type:
			citation.source_type === 'thread'
				? 'thread'
				: citation.source_type === 'note'
					? 'note'
					: citation.source_type === 'file'
						? 'file'
						: 'file',
		title: citation.title ?? '',
		href: citationUrl(citation),
		updatedAt: Date.now(),
		createdAt: Date.now(),
	})
</script>

{#if citation.source_type === 'note'}
	<NoteWidget {resource} {layout} class={className} />
{:else if citation.source_type === 'thread'}
	<ChatWidget {resource} {layout} class={className} />
{:else if citation.source_type === 'file'}
	<FileWidget {resource} {layout} class={className} />
{:else if citation.source_type === 'url'}
	<UrlWidget {resource} {layout} class={className} />
{:else}
	<!-- memory / tool_result: fall back to url widget style -->
	<UrlWidget {resource} {layout} class={className} />
{/if}
