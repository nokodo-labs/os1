<script lang="ts">
	import type { components } from '$lib/api/types'
	import { getSourceConfig } from '$lib/citations/config'
	import type { ResourceItem, ResourceType } from './types'

	type Citation = components['schemas']['Citation']

	interface Props {
		citation: Citation
		layout?: 'grid' | 'list'
		class?: string
	}

	let { citation, layout = 'grid', class: className = '' }: Props = $props()

	const cfg = $derived(getSourceConfig(citation.source_type))

	const resource: ResourceItem = $derived({
		id: citation.source_id,
		type: cfg.resourceType as ResourceType,
		title: citation.title ?? '',
		href: cfg.href(citation.source_id),
		updatedAt: Date.now(),
		createdAt: Date.now(),
	})

	const WidgetComponent = $derived(cfg.widget())
</script>

{#await WidgetComponent then mod}
	<mod.default {resource} {layout} class={className} />
{/await}
