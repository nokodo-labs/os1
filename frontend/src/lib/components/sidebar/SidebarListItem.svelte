<script lang="ts">
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import type { Snippet } from 'svelte'

	type ActionsVisibility = 'always' | 'hover'

	interface Props {
		selected?: boolean
		onSelect?: () => void | Promise<void>
		onPrefetch?: () => void
		actionsVisibility?: ActionsVisibility
		showChevron?: boolean
		radiusClass?: string
		paddingClass?: string
		className?: string
		children?: Snippet
		leading?: Snippet
		actions?: Snippet
	}

	let {
		selected = false,
		onSelect,
		onPrefetch,
		actionsVisibility = 'hover',
		showChevron = false,
		radiusClass = 'rounded-pill',
		paddingClass = 'px-3 py-2.5',
		className = '',
		children,
		leading,
		actions,
	}: Props = $props()

	function handleKeyDown(event: KeyboardEvent) {
		if (event.key !== 'Enter' && event.key !== ' ') return
		event.preventDefault()
		void onSelect?.()
	}
</script>

<div
	role="button"
	tabindex="0"
	class={`group/sidebar-item ${radiusClass} flex w-full min-w-0 cursor-pointer items-center gap-3 border border-transparent bg-transparent ${paddingClass} text-left transition-all duration-200 hover:border-white/10 hover:bg-white/5 ${selected ? 'shadow-[inset_0_2px_8px_rgba(255,255,255,0.1)]' : ''} ${className}`}
	style={selected
		? 'background-color: var(--accent-bg); border-color: var(--accent-border);'
		: ''}
	onmouseenter={() => onPrefetch?.()}
	onclick={() => void onSelect?.()}
	onkeydown={handleKeyDown}
>
	{#if leading}
		{@render leading()}
	{/if}

	<div class="min-w-0 flex-1">
		{@render children?.()}
	</div>

	{#if actions}
		<div
			class={`shrink-0 ${actionsVisibility === 'always' ? 'opacity-100' : 'opacity-0 group-hover/sidebar-item:opacity-100'} transition-opacity duration-150`}
		>
			{@render actions()}
		</div>
	{/if}

	{#if showChevron}
		<ChevronRight
			className="h-4 w-4 shrink-0 text-white/35 transition-colors group-hover/sidebar-item:text-white/55"
		/>
	{/if}
</div>
