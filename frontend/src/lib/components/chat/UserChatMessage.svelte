<script lang="ts">
	import type { Snippet } from 'svelte'

	interface Props {
		content: string
		timestamp?: Date
		actions?: Snippet
	}

	let { content, timestamp, actions }: Props = $props()

	let showActions = $state(false)
	let hideTimeout: number | null = null

	function handleMouseEnter() {
		if (hideTimeout) {
			clearTimeout(hideTimeout)
			hideTimeout = null
		}
		showActions = true
	}

	function handleMouseLeave() {
		showActions = false
		if (hideTimeout) {
			clearTimeout(hideTimeout)
			hideTimeout = null
		}
	}
</script>

<div
	class="ml-auto flex max-w-[80%] animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] flex-col items-end gap-2 self-end"
	onmouseenter={handleMouseEnter}
	onmouseleave={handleMouseLeave}
	role="article"
>
	<div
		class="liquid-glass relative rounded-3xl px-5 py-4 backdrop-blur-[20px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] [backdrop-saturate:180%] before:pointer-events-none before:absolute before:inset-0 before:rounded-[inherit] before:bg-linear-to-br before:from-white/40 before:to-white/10 before:mask-exclude before:p-px before:content-[''] before:[-webkit-mask-composite:xor] before:[-webkit-mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)] before:[mask:linear-gradient(#fff_0_0)_content-box,linear-gradient(#fff_0_0)] hover:-translate-y-0.5"
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
		{#if timestamp}
			<div class="mt-2 text-xs text-black/50 dark:text-white/50">
				{timestamp
					.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
					.toLowerCase()}
			</div>
		{/if}
	</div>

	{#if actions}
		<div
			class="flex gap-2 px-2 transition-opacity duration-200 {showActions
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
