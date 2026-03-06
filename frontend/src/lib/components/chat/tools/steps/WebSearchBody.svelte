<script lang="ts">
	import Search from '$lib/components/icons/Search.svelte'
	import type { ToolExecution } from '$lib/tools'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	/** parse search queries from tool events payload */
	let searchQueries = $derived.by(() => {
		for (const event of execution.events) {
			const queries = event.data.payload?.queries
			if (Array.isArray(queries)) {
				return queries.filter((q): q is string => typeof q === 'string')
			}
		}
		// fallback: use the tool call query argument
		const query = execution.toolCall.arguments.query
		if (typeof query === 'string' && query) return [query]
		return []
	})

	/** parse sources from events or result */
	let sources = $derived.by(() => {
		// check events for sources payload
		for (const event of execution.events) {
			const s = event.data.payload?.sources
			if (Array.isArray(s)) {
				return s
					.filter(
						(item): item is { url: string; title?: string } =>
							typeof item === 'object' &&
							item !== null &&
							typeof item.url === 'string'
					)
					.map((item) => ({
						url: item.url,
						title: item.title ?? null,
						domain: safeHostname(item.url),
					}))
			}
		}
		// fallback: parse result text for "N. title - url" pattern
		if (execution.result && !execution.result.isError) {
			return parseSourcesFromText(execution.result.output)
		}
		return []
	})

	function safeHostname(url: string): string {
		try {
			return new URL(url).hostname.replace(/^www\./, '')
		} catch {
			return url
		}
	}

	function faviconUrl(url: string): string {
		const domain = safeHostname(url)
		return `https://www.google.com/s2/favicons?sz=32&domain=${domain}`
	}

	function parseSourcesFromText(
		text: string
	): Array<{ url: string; title: string | null; domain: string }> {
		const results: Array<{ url: string; title: string | null; domain: string }> = []
		const lines = text.split('\n')
		for (const line of lines) {
			// match "N. label - https://..." pattern
			const match = line.match(/^\d+\.\s*(.+?)\s*-\s*(https?:\/\/\S+)/)
			if (match) {
				const title = match[1].trim()
				const url = match[2].trim()
				results.push({ url, title: title || null, domain: safeHostname(url) })
			}
		}
		return results
	}
</script>

<div class="space-y-2">
	<!-- search query pills -->
	{#if searchQueries.length > 0}
		<div class="flex flex-wrap gap-1.5">
			{#each searchQueries as query (query)}
				<div
					class="bg-foreground/5 text-foreground/80 flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs"
				>
					<Search class="text-foreground/60 h-3 w-3 shrink-0" />
					<span class="line-clamp-1">{query}</span>
				</div>
			{/each}
		</div>
	{/if}

	<!-- source cards -->
	{#if sources.length > 0}
		<div class="space-y-0.5">
			{#each sources as source (source.url)}
				<a
					href={source.url}
					target="_blank"
					rel="noopener noreferrer external"
					data-sveltekit-preload-data="off"
					class="hover:bg-foreground/5 flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 transition-colors"
				>
					<img
						src={faviconUrl(source.url)}
						alt=""
						class="h-4 w-4 shrink-0 rounded-sm"
						loading="lazy"
						onerror={(e) => {
							const img = e.currentTarget as HTMLImageElement
							img.style.display = 'none'
						}}
					/>
					<span class="text-foreground/80 min-w-0 flex-1 truncate text-xs">
						{source.title || source.domain}
					</span>
					{#if source.title}
						<span class="text-foreground/40 shrink-0 text-xs">{source.domain}</span>
					{/if}
				</a>
			{/each}
		</div>
	{/if}
</div>
