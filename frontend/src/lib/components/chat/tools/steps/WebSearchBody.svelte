<script lang="ts">
	import Search from '$lib/components/icons/Search.svelte'
	import type { ToolExecution } from '$lib/tools'
	import {
		getWebSearchProgressItems,
		getWebSearchQueries,
		getWebSearchSources,
	} from '$lib/tools/webSearch'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	let searchQueries = $derived(getWebSearchQueries(execution))
	let progressItems = $derived(getWebSearchProgressItems(execution))
	let sources = $derived(getWebSearchSources(execution))

	function faviconUrl(url: string): string {
		const domain = sources.find((source) => source.url === url)?.domain ?? url
		return `https://www.google.com/s2/favicons?sz=32&domain=${domain}`
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

	<!-- progress timeline -->
	{#if progressItems.length > 0}
		<div class="space-y-1">
			{#each progressItems as item (item.id)}
				<div class="text-foreground/55 flex items-center gap-2 px-1 text-xs">
					<span class="bg-foreground/25 h-1.5 w-1.5 shrink-0 rounded-full"></span>
					<span class="min-w-0 flex-1 truncate">{item.message}</span>
					{#if item.resultCount !== null}
						<span class="text-foreground/35 shrink-0 tabular-nums">
							{item.resultCount}
							{item.resultCount === 1 ? 'result' : 'results'}
						</span>
					{:else if item.sourceCount !== null}
						<span class="text-foreground/35 shrink-0 tabular-nums">
							{item.sourceCount}
							{item.sourceCount === 1 ? 'source' : 'sources'}
						</span>
					{/if}
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
