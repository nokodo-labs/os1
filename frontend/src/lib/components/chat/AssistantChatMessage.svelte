<script lang="ts">
	import Timestamp from '$lib/components/Timestamp.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import ExclamationTriangle from '$lib/components/icons/ExclamationTriangle.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Snippet } from 'svelte'
	import { onMount } from 'svelte'
	import type { Action } from 'svelte/action'
	import ChatGptLoadingIndicator from './ChatGptLoadingIndicator.svelte'

	interface Props {
		content: string
		timestamp?: Date
		actions?: Snippet
		persistentActions?: Snippet
		lead?: Snippet
		tail?: Snippet
		isLastMessage?: boolean
		isStreaming?: boolean
		isRunActive?: boolean
		showStreamingPlaceholder?: boolean
		modelName?: string
		avatarUrl?: string | null
		tone?: 'default' | 'error'
		siblingCount?: number
		currentSiblingIndex?: number
		onPrevious?: () => void
		onNext?: () => void
	}

	let {
		content,
		timestamp,
		actions,
		persistentActions,
		lead,
		tail,
		isLastMessage = false,
		isStreaming = false,
		isRunActive = false,
		showStreamingPlaceholder = true,
		modelName = 'assistant',
		avatarUrl = null,
		tone = 'default',
		siblingCount = 0,
		currentSiblingIndex = 0,
		onPrevious,
		onNext,
	}: Props = $props()

	let hasContent = $derived(content.trim().length > 0)
	let showActions = $state(false)
	let isHovered = $state(false)
	let avatarError = $state(false)

	// derived visibility - keeps the template readable
	let actionsVisible = $derived(!isStreaming && !isRunActive && (isLastMessage || showActions))
	// tree/branch switcher is always visible when multiple siblings exist
	let branchNavVisible = $derived(siblingCount > 1)

	// intentionally non-reactive - synchronous flag between touch + click handlers.
	// first tap reveals actions, the captured click is swallowed so buttons aren't triggered.
	let justRevealed = false
	const instanceId = Math.random().toString(36).slice(2)
	const ACTIONS_EVENT = 'chat-message-actions-open'
	let touchStartX = 0
	let touchStartY = 0
	let touchMoved = false
	let touchActive = false
	// timestamp of the last touch interaction - used to ignore synthetic mouse
	// events that mobile browsers fire after a touch sequence
	let lastTouchTime = 0
	let messageRef: HTMLElement | undefined = $state()

	function handleMouseEnter() {
		// ignore synthetic mouse events fired by the browser after a touch
		if (Date.now() - lastTouchTime < 500) return
		showActions = true
		isHovered = true
	}

	function handleMouseLeave() {
		if (Date.now() - lastTouchTime < 500) return
		showActions = false
		isHovered = false
	}

	function openActions() {
		if (isLastMessage) {
			showActions = false
			isHovered = true
			window.dispatchEvent(new CustomEvent(ACTIONS_EVENT, { detail: { id: instanceId } }))
			return
		}
		showActions = true
		isHovered = true
		justRevealed = true
		window.dispatchEvent(new CustomEvent(ACTIONS_EVENT, { detail: { id: instanceId } }))
		// safety net: clear if click never fires (e.g. scroll intercepts the tap)
		setTimeout(() => {
			justRevealed = false
		}, 400)
	}

	function handleTouchStart(e: TouchEvent) {
		lastTouchTime = Date.now()
		if (showActions) return
		if (e.touches.length !== 1) return
		touchActive = true
		touchMoved = false
		const t = e.touches[0]
		touchStartX = t.clientX
		touchStartY = t.clientY
	}

	function handleTouchMove(e: TouchEvent) {
		if (!touchActive) return
		if (e.touches.length !== 1) return
		const t = e.touches[0]
		if (Math.abs(t.clientX - touchStartX) > 8 || Math.abs(t.clientY - touchStartY) > 8) {
			touchMoved = true
		}
	}

	function handleTouchEnd() {
		if (!touchActive) return
		touchActive = false
		if (touchMoved) return
		openActions()
	}

	function handleTouchCancel() {
		if (!touchActive) return
		touchActive = false
	}

	onMount(() => {
		const handler = (ev: Event) => {
			const e = ev as CustomEvent<{ id?: string }>
			if (e.detail?.id === instanceId) return
			showActions = false
			isHovered = false
		}
		window.addEventListener(ACTIONS_EVENT, handler as globalThis.EventListener)
		return () => {
			window.removeEventListener(ACTIONS_EVENT, handler as globalThis.EventListener)
		}
	})

	// dismiss touch-revealed actions when tapping outside this message
	$effect(() => {
		if (!showActions && !isHovered) return
		const dismiss = (e: TouchEvent) => {
			lastTouchTime = Date.now()
			if (messageRef?.contains(e.target as Node)) return
			showActions = false
			isHovered = false
		}
		document.addEventListener('touchstart', dismiss, { passive: true })
		return () => document.removeEventListener('touchstart', dismiss)
	})

	const captureClick: Action = (node) => {
		const handler = (e: Event) => {
			if (justRevealed) {
				e.stopPropagation()
				e.preventDefault()
				justRevealed = false
			}
		}
		node.addEventListener('click', handler, { capture: true })
		return {
			destroy() {
				node.removeEventListener('click', handler, { capture: true })
			},
		}
	}
</script>

<div
	bind:this={messageRef}
	class="flex w-full animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] items-start gap-3 self-start
        {device.isMobile ? 'px-2' : ''}"
	onmouseenter={handleMouseEnter}
	onmouseleave={handleMouseLeave}
	ontouchstart={handleTouchStart}
	ontouchmove={handleTouchMove}
	ontouchend={handleTouchEnd}
	ontouchcancel={handleTouchCancel}
	role="article"
	aria-label="{modelName} message"
>
	<!-- avatar - hidden on mobile to reclaim full width -->
	{#if !device.isMobile}
		<div
			class="assistant-avatar border-foreground/10 bg-foreground/5 mt-1 h-10 w-10 shrink-0 overflow-hidden rounded-full border"
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
					<Sparkles variant="solid" class="text-foreground/90 h-5 w-5" />
				</div>
			{/if}
		</div>
	{/if}

	<!-- content container -->
	<div class="relative flex min-w-0 flex-1 flex-col gap-2">
		<div class="flex items-center gap-2">
			<span class="text-foreground/90 text-base font-bold">{modelName}</span>
			{#if timestamp}
				<Timestamp
					{timestamp}
					className="text-xs text-foreground/50 transition-opacity duration-200 {isHovered
						? 'opacity-100'
						: 'opacity-0'}"
				/>
			{/if}
		</div>

		{#if lead}
			<div class="space-y-3">{@render lead()}</div>
		{/if}

		{#if tone === 'error'}
			<div
				class="border-destructive/30 bg-destructive/10 rounded-container flex items-start gap-3 border px-4 py-3"
			>
				<div
					class="bg-destructive/15 text-destructive mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
				>
					<ExclamationTriangle class="h-4 w-4" strokeWidth="2" />
				</div>
				<div class="min-w-0 flex-1 space-y-0.5">
					<div class="text-destructive text-sm font-semibold">something went wrong</div>
					<MarkdownRenderer
						{content}
						{isStreaming}
						class="assistant-markdown text-destructive/90 **:text-destructive/90! text-[0.9rem] leading-relaxed wrap-break-word"
					/>
				</div>
			</div>
		{:else if isStreaming && !hasContent && showStreamingPlaceholder}
			<div class="assistant-markdown text-foreground/60 text-[0.95rem] leading-relaxed">
				<div class="my-3">
					<ChatGptLoadingIndicator />
				</div>
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

		<!-- branch nav + action buttons -->
		<div class="flex items-center gap-2">
			{#if siblingCount > 1}
				<div
					class="text-foreground/50 mr-1 flex h-6 items-center text-xs font-medium transition-opacity duration-200 select-none
                        {branchNavVisible ? 'opacity-100' : 'pointer-events-none opacity-0'}"
					role="none"
					use:captureClick
				>
					<button
						class="text-foreground/80 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
						disabled={currentSiblingIndex === 0}
						onclick={onPrevious}
						title="previous version"
					>
						<ChevronLeft class="size-4" strokeWidth="2" />
					</button>
					<span class="mx-0.5 font-mono tabular-nums">
						{currentSiblingIndex + 1}/{siblingCount}
					</span>
					<button
						class="text-foreground/80 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
						disabled={currentSiblingIndex === siblingCount - 1}
						onclick={onNext}
						title="next version"
					>
						<ChevronRight class="size-4" strokeWidth="2" />
					</button>
				</div>
			{/if}

			{#if persistentActions}
				<div class="flex items-center gap-2" role="none" use:captureClick>
					{@render persistentActions()}
				</div>
			{/if}

			{#if actions}
				<div
					class="flex items-center gap-2 transition-opacity duration-200
                        {actionsVisible ? 'opacity-100' : 'pointer-events-none opacity-0'}"
					role="none"
					use:captureClick
				>
					{@render actions()}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.assistant-avatar {
		box-shadow:
			0 10px 15px -3px var(--accent-shadow),
			0 4px 6px -2px var(--accent-shadow);
	}

	:global(.assistant-markdown) {
		word-break: break-word;
	}

	:global(.assistant-markdown p) {
		margin-top: 0.75rem;
		margin-bottom: 0.75rem;
	}
</style>
