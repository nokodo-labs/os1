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
		class:tail-right={showTail && tailStyle === 'imessage' && align === 'right'}
		class:tail-left={showTail && tailStyle === 'imessage' && align === 'left'}
	>
		<div
			class="bubble-content liquid-glass rounded-container relative px-5 py-4 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%]"
			style="
                background-color: var(--accent-primary);
                box-shadow: 0 4px 16px var(--accent-border);
            "
		>
			<div
				class="text-[0.95rem] leading-relaxed wrap-break-word whitespace-pre-wrap text-white/95"
			>
				{content}
			</div>
		</div>

		{#if showTail && tailStyle === 'imessage'}
			<svg
				class="tail-svg"
				class:tail-svg-right={align === 'right'}
				class:tail-svg-left={align === 'left'}
				width="12"
				height="19"
				viewBox="0 0 12 19"
				xmlns="http://www.w3.org/2000/svg"
			>
				{#if align === 'right'}
					<path
						d="M 0 0
                           C 0 6, 0 10, 4 14
                           C 8 17, 10 19, 12 19
                           L 0 19
                           Z"
						fill="var(--accent-primary)"
					/>
				{:else}
					<path
						d="M 12 0
                           C 12 6, 12 10, 8 14
                           C 4 17, 2 19, 0 19
                           L 12 19
                           Z"
						fill="var(--accent-primary)"
					/>
				{/if}
			</svg>
		{/if}
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
		display: inline-block;
	}

	/* tighten corner where tail attaches */
	.tail-right .bubble-content {
		border-bottom-right-radius: 4px !important;
	}

	.tail-left .bubble-content {
		border-bottom-left-radius: 4px !important;
	}

	/* SVG positioning */
	.tail-svg {
		position: absolute;
		bottom: 0;
		pointer-events: none;
	}

	.tail-svg-right {
		right: -8px;
	}

	.tail-svg-left {
		left: -8px;
	}
</style>
