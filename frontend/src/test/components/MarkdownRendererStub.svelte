<script lang="ts">
	/** stands in for MarkdownRenderer: streamdown pulls in css node cannot parse. */
	interface Props {
		content: string
		isStreaming?: boolean
		class?: string
		citations?: unknown[]
	}

	let { content }: Props = $props()
</script>

<div data-testid="markdown">{content}</div>
