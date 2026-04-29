<script lang="ts">
	import { getApiBaseUrl } from '$lib/api/client'
	import {
		extractFileParts,
		extractMediaParts,
		type FileContentPart,
		type MediaContentPart,
	} from '$lib/chat/helpers'
	import type { ApiMessage } from '$lib/chat/types'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import MessageActionButton from '$lib/components/chat/MessageActionButton.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { BubbleTailStyle } from '$lib/stores/preferences.svelte'
	import type { Snippet } from 'svelte'
	import { onMount, tick } from 'svelte'
	import type { Action } from 'svelte/action'

	interface Props {
		content: string
		contentParts?: ApiMessage['content']
		optimisticMediaParts?: MediaContentPart[]
		optimisticFileParts?: FileContentPart[]
		timestamp?: Date
		align?: 'left' | 'right'
		actions?: Snippet
		siblingCount?: number
		currentSiblingIndex?: number
		onPrevious?: () => void
		onNext?: () => void
		tailStyle?: BubbleTailStyle
		showTail?: boolean
		viewTransitionName?: string
		onEditSave?: (newContent: string) => Promise<void>
		onEditSaveAsCopy?: (newContent: string) => Promise<void>
	}

	let {
		content,
		contentParts,
		optimisticMediaParts,
		optimisticFileParts,
		timestamp,
		align = 'right',
		actions,
		siblingCount = 1,
		currentSiblingIndex = 0,
		onPrevious,
		onNext,
		tailStyle = 'none',
		showTail = false,
		viewTransitionName,
		onEditSave,
		onEditSaveAsCopy,
	}: Props = $props()

	const apiBase = getApiBaseUrl()
	const mediaParts = $derived(
		contentParts ? extractMediaParts(contentParts, apiBase) : (optimisticMediaParts ?? [])
	)
	const fileParts = $derived(
		contentParts ? extractFileParts(contentParts, apiBase) : (optimisticFileParts ?? [])
	)
	const hasMedia = $derived(mediaParts.length > 0 || fileParts.length > 0)

	let showActions = $state(false)
	let isHovered = $state(false)

	// edit state
	let isEditing = $state(false)
	let editContent = $state('')
	let editTextarea: HTMLTextAreaElement | undefined = $state()
	let isSaving = $state(false)

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
		if (!showActions) return
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

	function startEditing() {
		isEditing = true
		editContent = content
	}

	function cancelEditing() {
		isEditing = false
		editContent = ''
	}

	async function saveEdit() {
		if (!onEditSave || isSaving || !editContent.trim()) return
		isSaving = true
		try {
			await onEditSave(editContent.trim())
			isEditing = false
			editContent = ''
		} finally {
			isSaving = false
		}
	}

	async function saveAsCopy() {
		if (!onEditSaveAsCopy || isSaving || !editContent.trim()) return
		isSaving = true
		try {
			await onEditSaveAsCopy(editContent.trim())
			isEditing = false
			editContent = ''
		} finally {
			isSaving = false
		}
	}

	// focus & size the textarea when entering edit mode
	$effect(() => {
		if (!isEditing || !editTextarea) return
		const el = editTextarea
		void tick().then(() => {
			el.style.height = ''
			el.style.height = `${el.scrollHeight}px`
			el.focus()
			el.setSelectionRange(el.value.length, el.value.length)
		})
	})

	const canEdit = $derived(!!(onEditSave || onEditSaveAsCopy))
</script>

<div
	bind:this={messageRef}
	class="flex animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] flex-col gap-2"
	class:ml-auto={align === 'right' && !isEditing}
	class:items-end={align === 'right' && !isEditing}
	class:items-start={align === 'left' && !isEditing}
	class:items-stretch={isEditing}
	class:w-full={isEditing}
	style:max-width={!isEditing ? '80%' : undefined}
	onmouseenter={handleMouseEnter}
	onmouseleave={handleMouseLeave}
	ontouchstart={handleTouchStart}
	ontouchmove={handleTouchMove}
	ontouchend={handleTouchEnd}
	ontouchcancel={handleTouchCancel}
	role="article"
>
	{#if timestamp && !isEditing}
		<Timestamp
			{timestamp}
			className="text-xs text-foreground/50 transition-opacity duration-200 {isHovered
				? 'opacity-100'
				: 'opacity-0'}"
		/>
	{/if}

	<!-- media attachments rendered OUTSIDE the bubble -->
	{#if hasMedia && !isEditing}
		<div class="max-w-sm space-y-1.5 overflow-hidden rounded-2xl">
			<MediaAttachments {mediaParts} {fileParts} />
		</div>
	{/if}

	<!-- text bubble (only shown when there is text content or editing) -->
	{#if content.trim().length > 0 || isEditing}
		<div
			class="bubble-wrapper"
			class:w-full={isEditing}
			class:imessage-right={!isEditing &&
				showTail &&
				tailStyle === 'imessage' &&
				align === 'right'}
			class:imessage-left={!isEditing &&
				showTail &&
				tailStyle === 'imessage' &&
				align === 'left'}
			class:whatsapp-right={!isEditing &&
				showTail &&
				tailStyle === 'whatsapp' &&
				align === 'right'}
			class:whatsapp-left={!isEditing &&
				showTail &&
				tailStyle === 'whatsapp' &&
				align === 'left'}
		>
			<div
				class="bubble-content liquid-glass relative rounded-3xl px-3 py-2 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%]"
				class:px-5={isEditing}
				class:py-3={isEditing}
				class:w-full={isEditing}
				style:view-transition-name={viewTransitionName}
				style="background-color: var(--accent-primary); box-shadow: 0 4px 16px var(--accent-border);"
			>
				{#if isEditing}
					<div class="max-h-96 overflow-auto">
						<textarea
							bind:this={editTextarea}
							bind:value={editContent}
							class="text-foreground placeholder:text-foreground/40 w-full resize-none bg-transparent leading-relaxed wrap-break-word outline-none disabled:opacity-60"
							placeholder="edit your message"
							disabled={isSaving}
							rows={1}
							oninput={(e) => {
								const t = e.currentTarget
								t.style.height = ''
								t.style.height = `${t.scrollHeight}px`
							}}
							onkeydown={(e) => {
								if (e.key === 'Escape') cancelEditing()
								if (
									(e.metaKey || e.ctrlKey) &&
									e.key === 'Enter' &&
									onEditSaveAsCopy
								)
									saveAsCopy()
								if ((e.metaKey || e.ctrlKey) && e.key === 's') {
									e.preventDefault()
									if (onEditSave) saveEdit()
								}
							}}
						></textarea>
					</div>
					<!-- button row: save (left), cancel + send (right) -->
					<div class="mt-2 mb-1 flex justify-between text-sm font-medium">
						<div>
							{#if onEditSave}
								<button
									onclick={saveEdit}
									disabled={isSaving || !editContent.trim()}
									class="border-foreground/20 bg-foreground/10 text-foreground/90 hover:bg-foreground/20 cursor-pointer rounded-3xl border px-3.5 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-40"
								>
									save
								</button>
							{/if}
						</div>
						<div class="flex space-x-1.5">
							<button
								onclick={cancelEditing}
								disabled={isSaving}
								class="text-foreground/70 hover:bg-foreground/10 hover:text-foreground cursor-pointer rounded-3xl px-3.5 py-1.5 transition disabled:cursor-not-allowed disabled:opacity-50"
							>
								cancel
							</button>
							{#if onEditSaveAsCopy}
								<button
									onclick={saveAsCopy}
									disabled={isSaving || !editContent.trim()}
									class="bg-foreground text-background hover:bg-foreground/90 cursor-pointer rounded-3xl px-3.5 py-1.5 font-semibold transition disabled:cursor-not-allowed disabled:opacity-40"
								>
									{#if isSaving}
										<ShimmerText className="inline-block">saving</ShimmerText>
									{:else}
										send
									{/if}
								</button>
							{/if}
						</div>
					</div>
				{:else}
					<div
						class="text-foreground leading-relaxed wrap-break-word whitespace-pre-wrap"
					>
						{content}
					</div>
				{/if}
			</div>
		</div>
	{/if}

	{#if !isEditing && (actions || siblingCount > 1 || canEdit)}
		<div class="flex items-center gap-2 px-1" role="none">
			<div
				class="flex items-center gap-1 transition-opacity duration-200 {showActions
					? 'opacity-100'
					: 'pointer-events-none opacity-0'}"
				use:captureClick
			>
				{#if canEdit}
					<MessageActionButton onclick={startEditing} ariaLabel="edit message">
						<Pencil variant="solid" class="h-4 w-4" />
					</MessageActionButton>
				{/if}
				{#if actions}
					{@render actions()}
				{/if}
			</div>
			{#if siblingCount > 1}
				<div
					class="text-foreground/50 flex items-center text-xs font-medium select-none"
					role="none"
				>
					<button
						onclick={onPrevious}
						disabled={currentSiblingIndex === 0}
						class="text-foreground/50 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
						title="previous version"
					>
						<ChevronLeft class="size-4" strokeWidth="2" />
					</button>
					<span class="mx-0.5 font-mono tabular-nums">
						{currentSiblingIndex + 1}/{siblingCount}
					</span>
					<button
						onclick={onNext}
						disabled={currentSiblingIndex === siblingCount - 1}
						class="text-foreground/50 hover:text-foreground flex h-6 w-6 cursor-pointer items-center justify-center transition-transform duration-150 hover:scale-[1.05] active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100"
						title="next version"
					>
						<ChevronRight class="size-4" strokeWidth="2" />
					</button>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	@keyframes messageSlideIn {
		from {
			opacity: 0;
			filter: blur(2px);
			transform: translateY(34px) scale(0.92);
		}
		to {
			opacity: 1;
			filter: blur(0);
			transform: translateY(0) scale(1);
		}
	}

	.bubble-wrapper {
		position: relative;
		max-width: 100%;
	}

	/* ════════════════════════════════════════════════════════════
       iMESSAGE TAIL - Two-element technique (::before + ::after)
       ::before = colored tail shape
       ::after  = background cutout to shape the curve
       ════════════════════════════════════════════════════════════ */

	.imessage-right .bubble-content {
		border-bottom-right-radius: 4px !important;
	}

	.imessage-left .bubble-content {
		border-bottom-left-radius: 4px !important;
	}

	/* Common styles for both pseudo-elements */
	.imessage-right .bubble-content::before,
	.imessage-right .bubble-content::after,
	.imessage-left .bubble-content::before,
	.imessage-left .bubble-content::after {
		content: '';
		position: absolute;
		bottom: 0;
		height: 20px;
	}

	/* RIGHT TAIL (sent messages) */
	/* ::before - Colored tail shape */
	.imessage-right .bubble-content::before {
		right: -7px;
		width: 20px;
		background-color: var(--accent-primary);
		border-bottom-left-radius: 16px 14px; /* Elliptical radius for iOS curve */
	}

	/* ::after - Background cutout */
	.imessage-right .bubble-content::after {
		right: -26px;
		width: 26px;
		background-color: var(--chat-bg, var(--background));
		border-bottom-left-radius: 10px;
	}

	/* LEFT TAIL (received messages) */
	/* ::before - Colored tail shape */
	.imessage-left .bubble-content::before {
		left: -7px;
		width: 20px;
		background-color: var(--accent-primary);
		border-bottom-right-radius: 16px 14px; /* Mirrored elliptical radius */
	}

	/* ::after - Background cutout */
	.imessage-left .bubble-content::after {
		left: -26px;
		width: 26px;
		background-color: var(--chat-bg, var(--background));
		border-bottom-right-radius: 10px;
	}

	/* ════════════════════════════════════════════════════════════
       WHATSAPP TAIL - Single rotated pseudo-element with border trick
       ════════════════════════════════════════════════════════════ */

	/* WhatsApp uses sharper corners than iMessage */
	.whatsapp-right .bubble-content {
		border-radius: 8px !important;
		border-bottom-right-radius: 2px !important;
	}

	.whatsapp-left .bubble-content {
		border-radius: 8px !important;
		border-bottom-left-radius: 2px !important;
	}

	/* RIGHT TAIL (sent messages) */
	.whatsapp-right .bubble-content::after {
		content: '';
		position: absolute;
		bottom: 0;
		right: -8px;
		width: 0;
		height: 0;
		border: 0 solid transparent;
		border-top: 13px solid var(--accent-primary);
		border-radius: 0 20px 0;
		transform: rotate(145deg);
	}

	/* LEFT TAIL (received messages) */
	.whatsapp-left .bubble-content::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: -8px;
		width: 0;
		height: 0;
		border: 0 solid transparent;
		border-top: 13px solid var(--accent-primary);
		border-radius: 0 20px 0;
		transform: rotate(45deg) scaleY(-1);
	}
</style>
