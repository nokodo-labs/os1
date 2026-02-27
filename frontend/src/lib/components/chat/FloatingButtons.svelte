<script lang="ts">
	import { runChatStream } from '$lib/api/streaming'
	import ChatGptLoadingIndicator from '$lib/components/chat/ChatGptLoadingIndicator.svelte'
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import BlockQuote from '$lib/components/icons/BlockQuote.svelte'
	import ChatBubble from '$lib/components/icons/ChatBubble.svelte'
	import LightBulb from '$lib/components/icons/LightBulb.svelte'
	import XMark from '$lib/components/icons/XMark.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
	import { onDestroy, onMount, tick } from 'svelte'
	import { fade, fly } from 'svelte/transition'

	interface Props {
		threadId?: string | null
		onQuote?: (content: string) => void
	}

	let { threadId = null, onQuote }: Props = $props()

	let visible = $state(false)
	let position = $state({ top: 0, left: 0, right: -1, center: true })
	let selectedText = $state('')
	let mode = $state<'menu' | 'chat'>('menu')

	// mini-chat state
	type ChatPhase = 'idle' | 'loading' | 'thinking' | 'streaming' | 'done' | 'error'
	let chatOrigin = $state<'ask' | 'explain'>('ask')
	let chatQuery = $state('')
	let chatResponse = $state('')
	let chatError = $state('')
	let chatPhase = $state<ChatPhase>('idle')
	let chatAbortController: AbortController | null = null

	let container = $state<HTMLElement | null>(null)
	let chatInputEl = $state<HTMLInputElement | null>(null)
	let selectionDebounce: ReturnType<typeof setTimeout> | null = null

	const chatInputDisabled = $derived(
		chatPhase === 'loading' || chatPhase === 'thinking' || chatPhase === 'streaming'
	)

	function updateFromSelection() {
		const selection = window.getSelection()
		if (!selection || selection.toString().trim().length === 0) {
			if (mode === 'menu') close()
			return
		}

		if (container && container.contains(selection.anchorNode)) return

		const anchor = selection.anchorNode
		const anchorElement = anchor instanceof Element ? anchor : (anchor?.parentElement ?? null)
		if (!anchorElement?.closest('.assistant-markdown')) {
			if (mode === 'menu') close()
			return
		}

		selectedText = selection.toString().trim()

		const range = selection.getRangeAt(0)
		const rect = range.getBoundingClientRect()
		const vw = window.innerWidth
		const vh = window.innerHeight
		const pad = 12

		// prefer below selection, flip above if not enough space
		const spaceBelow = vh - rect.bottom - 8
		const popupEstHeight = mode === 'menu' ? 48 : 360
		let top: number
		if (spaceBelow < popupEstHeight && rect.top > popupEstHeight + pad) {
			top = Math.max(pad, rect.top - 8)
		} else {
			top = Math.min(vh - pad, rect.bottom + 8)
		}

		const center = rect.left + rect.width / 2

		if (center > vw * 0.7) {
			position = { top, left: -1, right: Math.max(pad, vw - rect.right), center: false }
		} else {
			position = {
				top,
				left: Math.max(pad, Math.min(center, vw - pad)),
				right: -1,
				center: true,
			}
		}

		visible = true
	}

	function updatePosition(event: Event) {
		const target = event.target as Node | null
		if (target && container && container.contains(target)) return
		if (selectionDebounce) clearTimeout(selectionDebounce)
		selectionDebounce = setTimeout(updateFromSelection, 0)
	}

	function handlePointerDown(e: PointerEvent) {
		if (!visible) return
		const target = e.target as Node | null
		if (target && container?.contains(target)) return
		close()
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.key === 'Escape' && visible) {
			e.preventDefault()
			close()
		}
	}

	function close() {
		chatAbortController?.abort()
		visible = false
		mode = 'menu'
		chatQuery = ''
		chatResponse = ''
		chatError = ''
		chatPhase = 'idle'
		chatOrigin = 'ask'
		selectedText = ''
	}

	onMount(() => {
		document.addEventListener('mouseup', updatePosition)
		document.addEventListener('touchend', updatePosition, { passive: true })
		document.addEventListener('selectionchange', updatePosition)
		document.addEventListener('pointerdown', handlePointerDown)
		document.addEventListener('keydown', handleKeyDown)
	})

	onDestroy(() => {
		chatAbortController?.abort()
		if (selectionDebounce) clearTimeout(selectionDebounce)
		document.removeEventListener('mouseup', updatePosition)
		document.removeEventListener('touchend', updatePosition)
		document.removeEventListener('selectionchange', updatePosition)
		document.removeEventListener('pointerdown', handlePointerDown)
		document.removeEventListener('keydown', handleKeyDown)
	})

	function handleQuote() {
		if (!selectedText) return
		const quoted = selectedText
			.split('\n')
			.map((l) => `> ${l}`)
			.join('\n')
		onQuote?.(`${quoted}\n\n`)
		window.getSelection()?.removeAllRanges()
		close()
	}

	async function handleAsk() {
		chatOrigin = 'ask'
		chatQuery = ''
		chatResponse = ''
		chatError = ''
		chatPhase = 'idle'
		mode = 'chat'
		updateFromSelection()
		await tick()
		if (!device.isMobile) chatInputEl?.focus()
	}

	function handleExplain() {
		if (!selectedText) return
		chatOrigin = 'explain'
		chatQuery = ''
		chatResponse = ''
		chatError = ''
		chatPhase = 'idle'
		mode = 'chat'
		updateFromSelection()
		void runChat(`explain this clearly and concisely:\n\n${selectedText}`)
	}

	async function runChat(question: string) {
		if (!selectedAgent.id) {
			chatError = 'no agent selected'
			chatPhase = 'error'
			return
		}
		chatAbortController?.abort()
		chatAbortController = new AbortController()
		chatPhase = 'loading'
		chatResponse = ''
		chatError = ''

		try {
			const stream = runChatStream({
				agentId: selectedAgent.id,
				threadId: threadId ?? null,
				input: question,
				persist: false,
				signal: chatAbortController.signal,
			})
			for await (const event of stream) {
				if (event.event === 'text_delta') {
					chatPhase = 'streaming'
					chatResponse += event.data.text
				} else if (event.event === 'delta') {
					const d = event.data.delta as Record<string, unknown>
					if ((d?.tool ?? null) !== null && chatPhase === 'loading') {
						chatPhase = 'thinking'
					}
				} else if (event.event === 'error') {
					throw new Error(event.data.message)
				}
			}
			if (!chatResponse.trim()) throw new Error('empty response')
			chatPhase = 'done'
		} catch (err) {
			if (err instanceof Error && err.name === 'AbortError') return
			chatError =
				err instanceof Error && err.message ? err.message : 'failed to generate response'
			chatPhase = 'error'
		}
	}

	async function handleSubmitChat() {
		const question = chatQuery.trim()
		if (!question || chatInputDisabled) return
		const fullQuestion =
			chatOrigin === 'ask' && !chatResponse
				? `regarding the following text: "${selectedText}"\n\n${question}`
				: question
		chatQuery = ''
		await runChat(fullQuestion)
	}

	let posStyle = $derived.by(() => {
		const parts = [`top: ${position.top}px;`]
		if (position.right >= 0) {
			parts.push(`right: ${position.right}px;`, 'max-width: calc(100vw - 24px);')
		} else {
			parts.push(`left: ${position.left}px;`, 'max-width: calc(100vw - 24px);')
			if (position.center) parts.push('transform: translateX(-50%);')
		}
		return parts.join(' ')
	})
</script>

{#if visible}
	<div
		bind:this={container}
		class="fixed z-60 flex flex-col items-start"
		style={posStyle}
		transition:fade={{ duration: 120 }}
	>
		{#if mode === 'menu'}
			<LiquidGlass frosted class="rounded-popup flex items-center gap-1 p-1">
				<button
					class="interactive rounded-pill hover:bg-foreground/10 flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium"
					onclick={handleQuote}
				>
					<BlockQuote class="size-3.5" />
					quote
				</button>
				<div class="bg-foreground/15 h-4 w-px"></div>
				<button
					class="interactive rounded-pill hover:bg-foreground/10 flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium"
					onclick={handleAsk}
				>
					<ChatBubble class="size-3.5" />
					ask
				</button>
				<div class="bg-foreground/15 h-4 w-px"></div>
				<button
					class="interactive rounded-pill hover:bg-foreground/10 flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium"
					onclick={handleExplain}
				>
					<LightBulb class="size-3.5" />
					explain
				</button>
			</LiquidGlass>
		{:else if mode === 'chat'}
			<div transition:fly={{ y: 5, duration: 200 }} class="w-[min(92vw,28rem)]">
				<LiquidGlass frosted class="liquid-glass--clip rounded-popup">
					<!-- header -->
					<div class="flex items-center justify-between px-3 pt-2.5 pb-1.5">
						<span class="text-xs font-medium opacity-45">
							{chatOrigin === 'ask' ? 'ask' : 'explanation'}
						</span>
						<button
							class="flex size-6 items-center justify-center rounded-full opacity-40 transition-opacity hover:opacity-75"
							onclick={close}
						>
							<XMark class="size-3.5" />
						</button>
					</div>

					<!-- response area -->
					{#if chatPhase !== 'idle'}
						<div class="max-h-64 overflow-y-auto px-3 pb-2 text-sm">
							{#if chatPhase === 'loading'}
								<div class="py-1">
									<ChatGptLoadingIndicator size="sm" />
								</div>
							{:else if chatPhase === 'thinking'}
								<div class="py-1">
									<ShimmerText className="text-xs opacity-60"
										>thinking</ShimmerText
									>
								</div>
							{:else if chatPhase === 'error'}
								<p class="py-1 text-sm text-red-500">{chatError}</p>
							{:else}
								<MarkdownRenderer
									content={chatResponse}
									isStreaming={chatPhase === 'streaming'}
								/>
							{/if}
						</div>
					{/if}

					<!-- input footer: only shown before submission -->
					{#if chatPhase === 'idle'}
						<div class="px-2 pt-1 pb-2">
							<div
								class="border-foreground/10 bg-foreground/5 flex items-center gap-1.5 rounded-full border px-2 py-1"
							>
								<input
									bind:this={chatInputEl}
									type="text"
									class="min-w-0 flex-1 bg-transparent py-1 text-sm outline-none placeholder:opacity-40 disabled:opacity-40"
									placeholder={chatResponse
										? 'ask a follow-up...'
										: 'ask a question...'}
									bind:value={chatQuery}
									disabled={chatInputDisabled}
									onkeydown={(e) => {
										if (e.key === 'Enter') void handleSubmitChat()
										if (e.key === 'Escape') close()
									}}
								/>
								<button
									class="interactive text-foreground flex size-6 shrink-0 items-center justify-center rounded-full hover:brightness-110 disabled:pointer-events-none disabled:opacity-40"
									style="background-color: var(--accent-primary);"
									onclick={handleSubmitChat}
									disabled={!chatQuery.trim() || chatInputDisabled}
								>
									<ArrowUp class="size-3.5" />
								</button>
							</div>
						</div>
					{/if}
				</LiquidGlass>
			</div>
		{/if}
	</div>
{/if}
