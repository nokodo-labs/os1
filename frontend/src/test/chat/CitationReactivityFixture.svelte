<script lang="ts">
	import { computeBlockCitations } from '$lib/chat/helpers'
	import type { ApiCitation, StreamingAssistantState } from '$lib/chat/types'
	import { SvelteMap } from 'svelte/reactivity'

	interface Props {
		citationSources: SvelteMap<string, ApiCitation[]>
		streamingAssistant: StreamingAssistantState | null
	}

	let { citationSources, streamingAssistant }: Props = $props()
</script>

{#if streamingAssistant}
	{@const blockCitations = computeBlockCitations([], streamingAssistant, citationSources)}

	<div data-testid="debug-stream-sources">
		{(citationSources.get(streamingAssistant.messageId) ?? []).length}
	</div>
	<div data-testid="debug-content">{streamingAssistant.content}</div>
	<div data-testid="debug-block-citations">{blockCitations.length}</div>

	{#if blockCitations.length > 0}
		<div data-testid="sources-pill">sources: {blockCitations.length}</div>
	{/if}
{/if}
