<script lang="ts">
	import Tooltip from '$lib/components/common/Tooltip.svelte'
	import { renderMarkdownToHtml } from '$lib/markdown/render'
	import type { Snippet } from 'svelte'
	import { SvelteDate } from 'svelte/reactivity'

	interface Props {
		content: string
		timestamp?: { getTime: () => number }
		actions?: Snippet
		isLastMessage?: boolean
		modelName?: string
		tone?: 'default' | 'error'
	}

	let {
		content,
		timestamp,
		actions,
		isLastMessage = false,
		modelName = 'assistant',
		tone = 'default',
	}: Props = $props()

	let showActions = $state(false)
	let isHovered = $state(false)
	let renderedHtml = $derived(renderMarkdownToHtml(content))

	function handleMouseEnter() {
		showActions = true
		isHovered = true
	}

	function handleMouseLeave() {
		showActions = false
		isHovered = false
	}

	function formatRelativeTime(date: { getTime: () => number }): string {
		const base = new SvelteDate(date.getTime())
		const now = new SvelteDate()
		const today = new SvelteDate(now.getFullYear(), now.getMonth(), now.getDate())
		const yesterday = new SvelteDate(today)
		yesterday.setDate(today.getDate() - 1)
		const messageDate = new SvelteDate(base.getFullYear(), base.getMonth(), base.getDate())

		const timeStr = base
			.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
			.toLowerCase()

		if (messageDate.getTime() === today.getTime()) {
			return `today, ${timeStr}`
		} else if (messageDate.getTime() === yesterday.getTime()) {
			return `yesterday, ${timeStr}`
		}

		return base
			.toLocaleDateString([], {
				month: 'short',
				day: 'numeric',
				hour: 'numeric',
				minute: '2-digit',
			})
			.toLowerCase()
	}

	function formatFullDate(date: { getTime: () => number }): string {
		const base = new SvelteDate(date.getTime())

		return base
			.toLocaleDateString('en-US', {
				weekday: 'long',
				year: 'numeric',
				month: 'long',
				day: 'numeric',
				hour: 'numeric',
				minute: '2-digit',
			})
			.toLowerCase()
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
		class="mt-1 h-10 w-10 shrink-0 rounded-full shadow-lg"
		style="background-color: var(--accent-primary); box-shadow: 0 10px 15px -3px var(--accent-shadow), 0 4px 6px -2px var(--accent-shadow);"
	></div>

	<!-- Content container -->
	<div class="relative flex min-w-0 flex-1 flex-col gap-2">
		<!-- Header with model name and timestamp -->
		<div class="flex items-center gap-2">
			<span class="text-sm font-medium text-white/90">{modelName}</span>
			{#if timestamp}
				<Tooltip content={formatFullDate(timestamp)} placement="top">
					<span
						class="text-xs text-white/40 transition-opacity duration-200 {isHovered
							? 'opacity-100'
							: 'opacity-0'}"
					>
						{formatRelativeTime(timestamp)}
					</span>
				</Tooltip>
			{/if}
		</div>

		<!-- Message content -->
		{#if tone === 'error'}
			<div class="border-destructive/30 bg-destructive/10 rounded-2xl border px-4 py-3">
				<div
					class="text-destructive assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
				>
					<!-- eslint-disable-next-line svelte/no-at-html-tags -->
					{@html renderedHtml}
				</div>
			</div>
		{:else}
			<div
				class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word text-white [text-shadow:0_2px_20px_rgba(0,0,0,0.8)]"
			>
				<!-- eslint-disable-next-line svelte/no-at-html-tags -->
				{@html renderedHtml}
			</div>
		{/if}

		<!-- Actions -->
		{#if actions}
			<div
				class="flex gap-1.5 transition-opacity duration-200 {isLastMessage || showActions
					? 'opacity-100'
					: 'opacity-0'}"
			>
				{@render actions()}
			</div>
		{/if}
	</div>
</div>

<style>
	:global(.assistant-markdown pre) {
		white-space: pre-wrap;
		word-break: break-word;
	}

	:global(.assistant-markdown code) {
		white-space: pre-wrap;
	}

	:global(.assistant-markdown a) {
		text-decoration: underline;
	}

	:global(.assistant-markdown ul),
	:global(.assistant-markdown ol) {
		padding-left: 1.25rem;
	}

	@keyframes messageSlideIn {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}
</style>
