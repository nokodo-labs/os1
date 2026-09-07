<script lang="ts">
	import { buildSelectionPrompt, SelectionAssist } from '$lib/chat/selectionAssist.svelte'
	import SelectionAssistPanel from '$lib/components/chat/SelectionAssistPanel.svelte'
	import SelectionPopover from '$lib/components/chat/SelectionPopover.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import BlockQuote from '$lib/components/icons/BlockQuote.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import LightBulb from '$lib/components/icons/LightBulb.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { onDestroy, onMount } from 'svelte'

	interface Props {
		onQuote?: (content: string) => void
	}

	let { onQuote }: Props = $props()

	const assist = new SelectionAssist()

	let selectedText = $state('')
	/** the whole passage the selection came from - a thread-less run reads nothing else. */
	let contextText = $state('')
	let anchorRange = $state<Range | null>(null)
	let toolbarOpen = $state(false)
	let panelMode = $state<'ask' | 'explain' | null>(null)
	let selectionDebounce: ReturnType<typeof setTimeout> | null = null

	const canQuote = $derived(typeof onQuote === 'function')

	function closeToolbar(): void {
		toolbarOpen = false
	}

	function closePanel(): void {
		assist.reset()
		panelMode = null
		selectedText = ''
		contextText = ''
		anchorRange = null
	}

	function updateFromSelection(): void {
		// an open panel owns the anchor: the reader may select inside it, and the
		// question it is answering must not change under them.
		if (panelMode) return

		const selection = window.getSelection()
		const text = selection?.toString().trim() ?? ''
		if (!selection || !text || selection.rangeCount === 0) {
			closeToolbar()
			return
		}

		const anchor = selection.anchorNode
		const element = anchor instanceof Element ? anchor : (anchor?.parentElement ?? null)
		const passage = element?.closest('.assistant-markdown')
		if (!passage) {
			closeToolbar()
			return
		}

		selectedText = text
		contextText = passage.textContent?.trim() ?? ''
		anchorRange = selection.getRangeAt(0).cloneRange()
		toolbarOpen = true
	}

	function scheduleUpdate(): void {
		if (selectionDebounce) clearTimeout(selectionDebounce)
		selectionDebounce = setTimeout(updateFromSelection, 0)
	}

	onMount(() => {
		document.addEventListener('mouseup', scheduleUpdate)
		document.addEventListener('touchend', scheduleUpdate, { passive: true })
		document.addEventListener('selectionchange', scheduleUpdate)
	})

	onDestroy(() => {
		assist.stop()
		if (selectionDebounce) clearTimeout(selectionDebounce)
		document.removeEventListener('mouseup', scheduleUpdate)
		document.removeEventListener('touchend', scheduleUpdate)
		document.removeEventListener('selectionchange', scheduleUpdate)
	})

	function handleQuote(): void {
		if (!selectedText) return
		const quoted = selectedText
			.split('\n')
			.map((line) => `> ${line}`)
			.join('\n')
		onQuote?.(`${quoted}\n\n`)
		window.getSelection()?.removeAllRanges()
		closeToolbar()
		closePanel()
	}

	function openAsk(): void {
		if (!selectedText) return
		assist.reset()
		panelMode = 'ask'
		closeToolbar()
	}

	function openExplain(): void {
		if (!selectedText) return
		assist.reset()
		panelMode = 'explain'
		closeToolbar()
		void assist.run(buildSelectionPrompt({ selection: selectedText, context: contextText }))
	}

	function askQuestion(question: string): void {
		void assist.run(
			buildSelectionPrompt({
				selection: selectedText,
				context: contextText,
				question,
				previousAnswer: assist.answer,
			})
		)
	}
</script>

<SelectionPopover
	open={toolbarOpen && !panelMode}
	anchor={anchorRange}
	onClose={closeToolbar}
	ariaLabel="selection actions"
	estimatedHeight={40}
>
	<LiquidGlass frosted class="rounded-popup flex items-center gap-1 p-1">
		{#if canQuote}
			<button
				type="button"
				class="rounded-pill hover:bg-foreground/10 flex cursor-pointer items-center gap-1.5 px-2 py-1.5 text-xs font-medium transition-colors"
				onclick={handleQuote}
			>
				<BlockQuote class="size-3.5" />
				quote
			</button>
			<div class="bg-foreground/15 h-4 w-px"></div>
		{/if}
		<button
			type="button"
			class="rounded-pill hover:bg-foreground/10 flex cursor-pointer items-center gap-1.5 px-2 py-1.5 text-xs font-medium transition-colors"
			onclick={openAsk}
		>
			<ChatBubble class="size-3.5" />
			ask
		</button>
		<div class="bg-foreground/15 h-4 w-px"></div>
		<button
			type="button"
			class="rounded-pill hover:bg-foreground/10 flex cursor-pointer items-center gap-1.5 px-2 py-1.5 text-xs font-medium transition-colors"
			onclick={openExplain}
		>
			<LightBulb class="size-3.5" />
			explain
		</button>
	</LiquidGlass>
</SelectionPopover>

<SelectionPopover
	open={panelMode !== null}
	anchor={anchorRange}
	onClose={closePanel}
	ariaLabel={panelMode === 'explain' ? 'explanation' : 'ask about the selected text'}
	estimatedHeight={220}
>
	<SelectionAssistPanel
		mode={panelMode ?? 'ask'}
		selection={selectedText}
		{assist}
		onClose={closePanel}
		onAsk={askQuestion}
		autofocus={panelMode === 'ask' && !device.isMobile}
	/>
</SelectionPopover>
