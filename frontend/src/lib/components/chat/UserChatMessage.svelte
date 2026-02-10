<script lang="ts">
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Timestamp from '$lib/components/Timestamp.svelte'
	import type { BubbleTailStyle } from '$lib/stores/preferences.svelte'
	import type { Snippet } from 'svelte'

	interface Props {
		content: string
		timestamp?: Date
		align?: 'left' | 'right'
		actions?: Snippet
		siblingCount?: number
		currentSiblingIndex?: number
		onPrevious?: () => void
		onNext?: () => void
		tailStyle?: BubbleTailStyle
		showTail?: boolean
	}

	let {
		content,
		timestamp,
		align = 'right',
		actions,
		siblingCount = 1,
		currentSiblingIndex = 0,
		onPrevious,
		onNext,
		tailStyle = 'none',
		showTail = false,
	}: Props = $props()

	let showActions = $state(false)
	let isHovered = $state(false)
	let hideTimeout: number | null = null

	function handleMouseEnter() {
		if (hideTimeout) {
			clearTimeout(hideTimeout)
			hideTimeout = null
		}
		showActions = true
		isHovered = true
	}

	function handleMouseLeave() {
		showActions = false
		isHovered = false
		if (hideTimeout) {
			clearTimeout(hideTimeout)
			hideTimeout = null
		}
	}
</script>

<div
	class="flex max-w-[80%] animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] flex-col gap-2"
	class:ml-auto={align === 'right'}
	class:items-end={align === 'right'}
	class:self-end={align === 'right'}
	class:items-start={align === 'left'}
	class:self-start={align === 'left'}
	onmouseenter={handleMouseEnter}
	onmouseleave={handleMouseLeave}
	role="article"
>
	{#if timestamp}
		<Timestamp
			{timestamp}
			className="text-xs text-black/50 transition-opacity duration-200 dark:text-white/50 {isHovered
				? 'opacity-100'
				: 'opacity-0'}"
		/>
	{/if}

	<div
		class="bubble-wrapper"
		class:imessage-right={showTail && tailStyle === 'imessage' && align === 'right'}
		class:imessage-left={showTail && tailStyle === 'imessage' && align === 'left'}
		class:whatsapp-right={showTail && tailStyle === 'whatsapp' && align === 'right'}
		class:whatsapp-left={showTail && tailStyle === 'whatsapp' && align === 'left'}
	>
		<div
			class="bubble-content liquid-glass relative rounded-3xl px-3 py-2 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%]"
			style="
                background-color: var(--accent-primary);
                box-shadow: 0 4px 16px var(--accent-border);
            "
		>
			<div class="leading-relaxed wrap-break-word whitespace-pre-wrap text-white">
				{content}
			</div>
		</div>
	</div>

	{#if actions || siblingCount > 1}
		<div
			class="flex items-center gap-1 px-1 transition-opacity duration-200 {showActions
				? 'opacity-100'
				: 'pointer-events-none opacity-0'}"
		>
			{#if siblingCount > 1}
				<div
					class="mr-2 flex items-center text-xs font-medium text-black/50 select-none dark:text-white/50"
				>
					<button
						onclick={onPrevious}
						disabled={currentSiblingIndex === 0}
						class="flex h-5 w-5 cursor-pointer items-center justify-center text-black/50 transition-transform duration-150 hover:scale-[1.1] hover:text-black active:scale-[0.95] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100 dark:text-white/50 dark:hover:text-white"
					>
						<ChevronLeft class="h-3 w-3" strokeWidth="2.5" />
					</button>
					<span class="mx-0.5 tabular-nums">
						{currentSiblingIndex + 1}/{siblingCount}
					</span>
					<button
						onclick={onNext}
						disabled={currentSiblingIndex === siblingCount - 1}
						class="flex h-5 w-5 cursor-pointer items-center justify-center text-black/50 transition-transform duration-150 hover:scale-[1.1] hover:text-black active:scale-[0.95] disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:scale-100 dark:text-white/50 dark:hover:text-white"
					>
						<ChevronRight class="h-3 w-3" strokeWidth="2.5" />
					</button>
				</div>
			{/if}
			{#if actions}
				{@render actions()}
			{/if}
		</div>
	{/if}
</div>

<style>
	@keyframes messageSlideIn {
		from {
			opacity: 0;
			transform: translateY(10px) scale(0.95);
		}
		to {
			opacity: 1;
			transform: translateY(0) scale(1);
		}
	}

	.bubble-wrapper {
		position: relative;
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
