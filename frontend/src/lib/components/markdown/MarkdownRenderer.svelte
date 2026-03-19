<script lang="ts">
	import { browser } from '$app/environment'
	import type { components } from '$lib/api/types'
	import Mermaid from '$lib/components/streamdown/Mermaid.svelte'
	import { tryUseDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { Streamdown, type Extension } from 'svelte-streamdown'
	import Code from 'svelte-streamdown/code'
	import Math from 'svelte-streamdown/math'

	type Citation = components['schemas']['Citation']

	type Props = {
		content: string
		class?: string
		isStreaming?: boolean
		citations?: Citation[]
	}

	let { content, class: className, isStreaming = false, citations = [] }: Props = $props()

	/** map citation source type to a navigable URL */
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
				return ''
		}
	}

	const sources = $derived(
		Object.fromEntries(
			citations.map((c) => [
				String(c.index),
				{ title: c.title ?? '', url: citationUrl(c) },
			])
		)
	)

	const debugUi = tryUseDebugUi()

	const animation = $derived(
		isStreaming
			? {
					enabled: debugUi?.streamdownAnimation.enabled ?? true,
					type: debugUi?.streamdownAnimation.type ?? 'fade',
					tokenize: debugUi?.streamdownAnimation.tokenize ?? 'word',
					duration: debugUi?.streamdownAnimation.duration ?? 450,
					animateOnMount: false,
				}
			: { enabled: false }
	)

	const defaultOrigin = browser ? window.location.origin : undefined

	// Allow all http/https links, plus relative links via defaultOrigin.
	// Streamdown's wildcard intentionally blocks non-http(s) schemes.
	const allowedLinkPrefixes = ['*']
	const allowedImagePrefixes = ['https://', 'http://', '/', 'data:image/']

	// Standard markdown-ish collapsible blocks, without enabling raw HTML.
	// Syntax:
	// :::details Optional summary
	// content
	// :::
	const detailsExtension: Extension = {
		name: 'details',
		level: 'block',
		tokenizer(src: string) {
			const match = src.match(/^:::details(?:\s+([^\n]+))?\n([\s\S]*?)\n:::(?:\n|$)/)
			if (!match) return undefined
			const summary = (match[1] ?? '').trim()
			const inner = match[2] ?? ''
			const tokens = this.lexer.blockTokens(inner)
			return {
				type: 'details',
				raw: match[0],
				summary,
				tokens,
			}
		},
	}

	// Theme overrides: keep Streamdown's structure but align backgrounds/borders to our palette.
	// Only uses existing Tailwind/shadcn tokens (bg-card/bg-muted/bg-popover/etc).
	const theme = {
		code: {
			container: 'bg-card/40 backdrop-blur-sm',
			header: 'bg-popover/40 backdrop-blur-sm',
			pre: 'bg-transparent',
		},
		codespan: {
			base: 'bg-card/40 border border-border/60 text-foreground',
		},
		table: {
			base: 'bg-card/20 backdrop-blur-sm',
		},
		thead: {
			base: 'bg-popover/30',
		},
		tr: {
			base: 'border-border border-b hover:bg-muted/30 transition-colors',
		},
		mermaid: {
			base: 'bg-card/20 backdrop-blur-sm',
		},
		components: {
			popover: 'liquid-glass--frosted',
			button: 'liquid-glass--frosted',
		},
		link: {
			blocked: 'text-muted-foreground',
		},
	} as const
</script>

<!-- trying to add static={!isStreaming} broke rendering of some types of markdown blocks. maybe fixed in future version of Streamdown -->
<Streamdown
	{content}
	class={className}
	parseIncompleteMarkdown={isStreaming}
	renderHtml={false}
	{defaultOrigin}
	{allowedLinkPrefixes}
	{allowedImagePrefixes}
	baseTheme="shadcn"
	{theme}
	{sources}
	inlineCitationsMode="carousel"
	extensions={[detailsExtension]}
	components={{
		code: Code,
		mermaid: Mermaid,
		math: Math,
	}}
	{animation}
>
	{#snippet children({ token, children })}
		{#if token.type === 'details'}
			<details class="border-border/60 bg-card/20 rounded-container my-3 border p-3">
				<summary class="text-foreground cursor-pointer text-sm font-medium select-none">
					{token.summary || 'details'}
				</summary>
				<div class="mt-2">
					{@render children()}
				</div>
			</details>
		{:else}
			{@render children?.()}
		{/if}
	{/snippet}
</Streamdown>
