<script lang="ts">
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import type { ToolExecution } from '$lib/tools'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	const url = $derived(
		typeof execution.toolCall.arguments.url === 'string'
			? execution.toolCall.arguments.url
			: null
	)

	const domain = $derived.by(() => {
		if (!url) return null
		try {
			return new URL(url).hostname.replace(/^www\./, '')
		} catch {
			return null
		}
	})

	const faviconSrc = $derived(
		domain ? `https://www.google.com/s2/favicons?sz=32&domain=${domain}` : null
	)
</script>

{#if url}
	<div class="mt-0.5 flex flex-col gap-1.5">
		<a
			href={url}
			target="_blank"
			rel="noopener noreferrer external"
			data-sveltekit-preload-data="off"
			class="flex items-center gap-2 rounded-lg py-1 text-sm transition-colors hover:bg-white/5"
		>
			{#if faviconSrc}
				<img
					src={faviconSrc}
					alt=""
					class="size-4 shrink-0 rounded-sm"
					loading="lazy"
					onerror={(e) => {
						const target = e.currentTarget as HTMLImageElement
						target.style.display = 'none'
					}}
				/>
			{:else}
				<GlobeAlt class="text-foreground/50 size-4 shrink-0" />
			{/if}
			<span class="text-foreground/60 truncate text-xs">{domain ?? url}</span>
		</a>
	</div>
{/if}
