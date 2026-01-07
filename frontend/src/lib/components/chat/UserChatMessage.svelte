<script lang="ts">
	import MessageTimestamp from '$lib/components/chat/MessageTimestamp.svelte'
	import type { Snippet } from 'svelte'

	interface Props {
		content: string
		timestamp?: Date
		align?: 'left' | 'right'
		actions?: Snippet
	}

	let { content, timestamp, align = 'right', actions }: Props = $props()

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
		<MessageTimestamp
			{timestamp}
			className="text-xs text-black/50 transition-opacity duration-200 dark:text-white/50 {isHovered
				? 'opacity-100'
				: 'opacity-0'}"
		/>
	{/if}

	<div
		class="liquid-glass rounded-container relative px-5 py-4 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%] before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:bg-linear-to-br before:from-white/40 before:to-white/10 before:mask-exclude before:p-px before:content-[''] before:[-webkit-mask-composite:xor] before:[-webkit-mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)] before:[mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)]"
		style="
            background: linear-gradient(to bottom right, var(--accent-shadow), var(--accent-bg));
            box-shadow: 0 4px 16px var(--accent-border);
        "
	>
		<div
			class="text-[0.95rem] leading-relaxed wrap-break-word text-black/95 dark:text-white/95"
		>
			{content}
		</div>
	</div>

	{#if actions}
		<div
			class="flex gap-1 px-1 transition-opacity duration-200 {showActions
				? 'opacity-100'
				: 'opacity-0'}"
		>
			{@render actions()}
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

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(-5px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}
</style>
