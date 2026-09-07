<script lang="ts">
	import type { SelectionAssist } from '$lib/chat/selectionAssist.svelte'
	import CopyButton from '$lib/components/chat/CopyButton.svelte'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import LightBulb from '$lib/components/icons/LightBulb.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import { IconButton } from '$lib/components/primitives'

	interface Props {
		mode: 'ask' | 'explain'
		/** the text the reader highlighted, shown back to them verbatim. */
		selection: string
		assist: SelectionAssist
		onClose: () => void
		onAsk: (question: string) => void
		autofocus?: boolean
	}

	let { mode, selection, assist, onClose, onAsk, autofocus = false }: Props = $props()

	/** longer than this and the quote is folded away until asked for. */
	const QUOTE_FOLD_CHARS = 180

	let question = $state('')
	let quoteExpanded = $state(false)
	let inputEl = $state<HTMLInputElement | null>(null)

	const foldable = $derived(selection.length > QUOTE_FOLD_CHARS)
	const hasAnswer = $derived(assist.answer.trim().length > 0)
	const failed = $derived(assist.phase === 'error')

	$effect(() => {
		if (autofocus) inputEl?.focus()
	})

	function submit(): void {
		const text = question.trim()
		if (!text || assist.isWorking) return
		question = ''
		onAsk(text)
	}
</script>

<LiquidMetal
	tag="div"
	class="rounded-popup border-foreground/12 bg-background/80 flex w-[min(92vw,26rem)] flex-col overflow-hidden border shadow-[0_24px_48px_rgba(12,10,30,0.55),inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-[18px]"
>
	<div class="flex items-center gap-1.5 px-3 pt-2.5 pb-1.5">
		{#if mode === 'explain'}
			<LightBulb class="text-foreground/40 size-3.5" />
		{:else}
			<ChatBubble class="text-foreground/40 size-3.5" />
		{/if}
		<span class="text-foreground/45 flex-1 text-[11px] font-semibold tracking-widest">
			{mode === 'explain' ? 'explanation' : 'ask about this'}
		</span>
		<IconButton size="xs" aria-label="close" title="close" onclick={onClose}>
			<XMark />
		</IconButton>
	</div>

	<div class="px-3 pb-2">
		<blockquote
			class="border-foreground/20 text-foreground/50 border-l-2 pl-2 text-xs leading-relaxed wrap-break-word {foldable &&
			!quoteExpanded
				? 'line-clamp-2'
				: 'max-h-24 overflow-y-auto'}"
		>
			{selection}
		</blockquote>
		{#if foldable}
			<button
				type="button"
				class="text-foreground/40 hover:text-foreground/70 mt-1 cursor-pointer pl-2 text-[11px] transition-colors"
				onclick={() => (quoteExpanded = !quoteExpanded)}
			>
				{quoteExpanded ? 'show less' : 'show more'}
			</button>
		{/if}
	</div>

	{#if assist.phase !== 'idle'}
		<div
			class="max-h-[min(20rem,45vh)] overflow-y-auto px-3 pb-2 text-sm"
			aria-live="polite"
			aria-busy={assist.isWorking}
		>
			{#if assist.phase === 'loading'}
				<ShimmerText className="text-xs">thinking</ShimmerText>
			{:else if assist.phase === 'thinking'}
				<ShimmerText className="text-xs">looking that up</ShimmerText>
			{:else}
				{#if hasAnswer}
					<MarkdownRenderer
						content={assist.answer}
						isStreaming={assist.phase === 'streaming'}
					/>
				{/if}
				{#if failed}
					<div class="text-foreground/60 flex items-start gap-1.5 pt-1 text-xs">
						<ExclamationTriangle class="mt-0.5 size-3.5 shrink-0 text-amber-500" />
						<span class="min-w-0 flex-1">{assist.errorMessage}</span>
					</div>
				{/if}
			{/if}
		</div>
	{/if}

	{#if (hasAnswer && !assist.isWorking) || assist.canRetry}
		<div class="flex items-center gap-1 px-2 pb-1.5">
			{#if hasAnswer}
				<CopyButton content={() => assist.answer} />
			{/if}
			{#if assist.canRetry}
				<button
					type="button"
					class="rounded-pill hover:bg-foreground/10 text-foreground/70 hover:text-foreground flex cursor-pointer items-center gap-1.5 px-2 py-1 text-xs font-medium transition-colors"
					onclick={() => void assist.retry()}
				>
					<ArrowPath class="size-3.5" />
					retry
				</button>
			{/if}
		</div>
	{/if}

	{#if mode === 'ask'}
		<div class="px-2 pt-0.5 pb-2">
			<div
				class="border-foreground/10 bg-foreground/5 flex items-center gap-1.5 rounded-full border px-2 py-1"
			>
				<input
					bind:this={inputEl}
					bind:value={question}
					type="text"
					class="min-w-0 flex-1 bg-transparent py-1 text-sm outline-none placeholder:opacity-40 disabled:opacity-40"
					placeholder={hasAnswer ? 'ask a follow-up...' : 'ask a question...'}
					aria-label="ask about the selected text"
					disabled={assist.isWorking}
					onkeydown={(event) => {
						if (event.key === 'Enter') submit()
						if (event.key === 'Escape') onClose()
					}}
				/>
				<IconButton
					size="xs"
					aria-label="send question"
					style="background-color: var(--foreground); color: var(--background);"
					disabled={!question.trim() || assist.isWorking}
					onclick={submit}
				>
					<ArrowUp strokeWidth="2.5" />
				</IconButton>
			</div>
		</div>
	{/if}
</LiquidMetal>
