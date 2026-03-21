<script lang="ts">
	import { browser } from '$app/environment'
	import type { components } from '$lib/api/types'
	import Brain from '$lib/components/icons/Brain.svelte'
	import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Mermaid from '$lib/components/streamdown/Mermaid.svelte'
	import CitationWidget from '$lib/components/widgets/CitationWidget.svelte'
	import { tryUseDebugUi } from '$lib/contexts/debugUiContext.svelte'
	import { Streamdown, type Extension } from 'svelte-streamdown'
	import Code from 'svelte-streamdown/code'
	import MathBlock from 'svelte-streamdown/math'

	type Citation = components['schemas']['Citation']

	/** streamdown's CitationToken shape (not publicly exported) */
	type CitationToken = { type: 'inline-citations'; keys: string[]; text: string; raw: string }

	type Props = {
		content: string
		class?: string
		isStreaming?: boolean
		citations?: Citation[]
	}

	let { content, class: className, isStreaming = false, citations = [] }: Props = $props()

	/** set of citation index strings for fast lookup ("1", "2", etc.) */
	const citationKeys = $derived(new Set(citations.map((c) => String(c.index))))

	/**
	 * normalize footnote-style citations to bracket style so streamdown
	 * can tokenize them. models sometimes emit [^n] / [^n]: ... instead
	 * of [n]. we rewrite inline refs and strip definition lines.
	 */
	const normalizedContent = $derived.by(() => {
		if (citationKeys.size === 0) return content
		let text = content
		// strip footnote definition lines: [^n]: ... (full line)
		text = text.replace(/^\[\^(\d+)\]:.*$/gm, (_, n) => (citationKeys.has(n) ? '' : _))
		// rewrite inline refs: [^n] -> [n]
		text = text.replace(/\[\^(\d+)\]/g, (full, n) => (citationKeys.has(n) ? `[${n}]` : full))
		return text
	})

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

	/** build a lookup from citation index to the full Citation object */
	const citationByIndex = $derived(new Map(citations.map((c) => [String(c.index), c])))

	/** sources for streamdown - enriched with full URL via defaultOrigin */
	const sources = $derived(
		Object.fromEntries(
			citations.map((c) => {
				const url = citationUrl(c)
				return [String(c.index), { title: c.title ?? '', url }]
			})
		)
	)

	/** resolve the first citation object from a CitationToken */
	function firstCitation(token: CitationToken): Citation | undefined {
		for (const key of token.keys) {
			const c = citationByIndex.get(key)
			if (c) return c
		}
		return undefined
	}

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
	content={normalizedContent}
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
		math: MathBlock,
	}}
	{animation}
>
	{#snippet inlineCitationPreview({
		token,
	}: {
		children: import('svelte').Snippet
		token: CitationToken
	})}
		{@const c = firstCitation(token)}
		{#if c}
			<span class="inline-flex items-center gap-1">
				{#if c.source_type === 'note'}
					<Document variant="solid" class="size-3.5 text-amber-400" />
				{:else if c.source_type === 'thread'}
					<ChatBubbles variant="solid" class="size-3.5 text-emerald-400" />
				{:else if c.source_type === 'file'}
					<Document variant="solid" class="size-3.5 text-rose-400" />
				{:else if c.source_type === 'url'}
					<GlobeAlt variant="solid" class="size-3.5 text-sky-400" />
				{:else if c.source_type === 'memory'}
					<Brain class="size-3.5 text-purple-400" />
				{:else if c.source_type === 'tool_result'}
					<CommandLine class="size-3.5 text-orange-400" />
				{/if}
				<span class="max-w-[18ch] truncate">{c.title || 'source'}</span>
			</span>
		{/if}
	{/snippet}

	{#snippet inlineCitationPopover({
		token,
	}: {
		children: import('svelte').Snippet
		token: CitationToken
	})}
		{#each token.keys as key (key)}
			{@const c = citationByIndex.get(key)}
			{#if c}
				<CitationWidget citation={c} layout="grid" />
			{/if}
		{/each}
	{/snippet}

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

<style>
	/* strip the dialog container styling for citation popovers so the
	   widget card IS the visual popover, not a card inside a card. */
	:global(dialog[data-streamdown-citation-popover]) {
		background: transparent;
		border: none;
		padding: 0;
		box-shadow: none;
		backdrop-filter: none;
		overflow: visible;
	}
	:global(dialog[data-streamdown-citation-popover]::before),
	:global(dialog[data-streamdown-citation-popover]::after) {
		content: none;
	}
</style>
