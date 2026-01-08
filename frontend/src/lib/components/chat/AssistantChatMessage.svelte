<script lang="ts">
	import Timestamp from '$lib/components/Timestamp.svelte'
	import SparklesSolid from '$lib/components/icons/SparklesSolid.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import type { Snippet } from 'svelte'

	interface Props {
		content: string
		timestamp?: { getTime: () => number }
		actions?: Snippet
		lead?: Snippet
		tail?: Snippet
		isLastMessage?: boolean
		isStreaming?: boolean
		modelName?: string
		avatarUrl?: string | null
		tone?: 'default' | 'error'
	}

	let {
		content,
		timestamp,
		actions,
		lead,
		tail,
		isLastMessage = false,
		isStreaming = false,
		modelName = 'assistant',
		avatarUrl = null,
		tone = 'default',
	}: Props = $props()

	let hasContent = $derived(content.trim().length > 0)

	let showActions = $state(false)
	let isHovered = $state(false)
	let avatarError = $state(false)

	function handleMouseEnter() {
		showActions = true
		isHovered = true
	}

	function handleMouseLeave() {
		showActions = false
		isHovered = false
	}
</script>

<div
	class="flex w-full animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] items-start gap-3 self-start"
	onmouseenter={handleMouseEnter}
	onmouseleave={handleMouseLeave}
	role="article"
>
	<!-- Avatar on the left -->
	<div
		class="mt-1 h-10 w-10 shrink-0 overflow-hidden rounded-full border border-white/10 bg-white/5 shadow-lg"
		style="box-shadow: 0 10px 15px -3px var(--accent-shadow), 0 4px 6px -2px var(--accent-shadow);"
	>
		{#if avatarUrl && !avatarError}
			<img
				src={avatarUrl}
				alt={modelName}
				class="h-full w-full object-cover"
				onerror={() => (avatarError = true)}
			/>
		{:else}
			<div
				class="flex h-full w-full items-center justify-center"
				style="background-color: var(--accent-primary);"
			>
				<SparklesSolid className="h-5 w-5 text-white/90" />
			</div>
		{/if}
	</div>

	<!-- Content container -->
	<div class="relative flex min-w-0 flex-1 flex-col gap-2">
		<div class="flex items-center gap-2">
			<span class="text-sm font-semibold text-white/90">{modelName}</span>
			{#if timestamp}
				<Timestamp
					{timestamp}
					className="text-xs text-white/40 transition-opacity duration-200 {isHovered
						? 'opacity-100'
						: 'opacity-0'}"
				/>
			{/if}
		</div>

		<!-- Message content -->
		{#if lead}
			<div class="space-y-3">{@render lead()}</div>
		{/if}

		{#if tone === 'error'}
			<div class="border-destructive/30 bg-destructive/10 rounded-2xl border px-4 py-3">
				<MarkdownRenderer
					{content}
					{isStreaming}
					class="assistant-markdown text-destructive **:text-destructive! text-[0.95rem] leading-relaxed wrap-break-word"
				/>
			</div>
		{:else if isStreaming && !hasContent}
			<div
				class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-[0.95rem] leading-relaxed text-white/60"
			>
				<span class="animate-pulse">thinking…</span>
			</div>
		{:else if hasContent}
			<MarkdownRenderer
				{content}
				{isStreaming}
				class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
			/>
		{/if}

		{#if tail}
			<div class="space-y-3">{@render tail()}</div>
		{/if}

		<!-- Actions -->
		{#if actions}
			<div
				class="flex gap-1 transition-opacity duration-200 {isLastMessage || showActions
					? 'opacity-100'
					: 'opacity-0'}"
			>
				{@render actions()}
			</div>
		{/if}
	</div>
</div>

<style>
	:global(.assistant-markdown) {
		word-break: break-word;
	}

	:global(.assistant-markdown p) {
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
	}
</style>
