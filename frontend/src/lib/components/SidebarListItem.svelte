<script lang="ts">
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import type { Snippet } from 'svelte'

	type ActionsVisibility = 'always' | 'hover' | 'reserve-hover' | 'overlay-always'

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
	class={`group/sidebar-item relative overflow-hidden ${radiusClass} flex w-full min-w-0 cursor-pointer items-center gap-3 border border-transparent bg-transparent ${paddingClass} hover:border-foreground/15 hover:bg-interactive-hover text-left transition-all duration-200 ${className}`}
	style={selected
		? 'background-color: rgb(var(--accent-rgb) / 0.3); border-color: rgb(var(--accent-rgb) / 0.55);'
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
		{#if actionsVisibility === 'always'}
			<div class="shrink-0">
				{@render actions()}
			</div>
		{:else if actionsVisibility === 'reserve-hover'}
			<div
				class="pointer-events-none shrink-0 opacity-0 transition-opacity duration-150 group-focus-within/sidebar-item:pointer-events-auto group-focus-within/sidebar-item:opacity-100 group-hover/sidebar-item:pointer-events-auto group-hover/sidebar-item:opacity-100"
			>
				{@render actions()}
			</div>
		{:else}
			<!-- overlay: no layout space taken; appears on top with gradient backdrop -->
			<div
				class="from-sidebar/90 absolute inset-y-0 right-0 flex items-center bg-linear-to-l to-transparent pr-2.5 pl-6 transition-opacity duration-150 {actionsVisibility ===
				'hover'
					? 'pointer-events-none opacity-0 group-hover/sidebar-item:pointer-events-auto group-hover/sidebar-item:opacity-100'
					: 'pointer-events-auto opacity-100'}"
			>
				{@render actions()}
			</div>
		{/if}
	{/if}

	{#if showChevron}
		<ChevronRight
			class="text-foreground/50 group-hover/sidebar-item:text-foreground/70 h-5 w-5 shrink-0 transition-colors"
		/>
	{/if}
</div>
