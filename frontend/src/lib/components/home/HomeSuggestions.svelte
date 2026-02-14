<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'
	import SearchIcon from '$lib/components/icons/Search.svelte'
	import '$lib/styles/liquid-glass.css'

	type IconComponent = typeof SearchIcon

	export type HomeSuggestion = {
		id: string
		title: string
		subtitle?: string
		icon: IconComponent
	}

	interface Props {
		open: boolean
		query: string
		suggestions: HomeSuggestion[]
		highlightedIndex: number
		onSelect: (suggestion: HomeSuggestion) => void
		onHighlight: (index: number) => void
	}

	let { open, suggestions, highlightedIndex, onSelect, onHighlight }: Props = $props()
</script>

{#if open && suggestions.length > 0}
	<LiquidGlass
		tag="div"
		class="rounded-container overflow-hidden shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
	>
		<div class="relative z-10">
			<div class="p-2" role="listbox" aria-label="suggestions">
				{#each suggestions as suggestion, index (suggestion.id)}
					{@const Icon = suggestion.icon}
					<button
						type="button"
						role="option"
						aria-selected={highlightedIndex >= 0 && index === highlightedIndex}
						class="rounded-pill flex w-full items-center gap-3 border-none px-3 py-2 text-left transition-colors {index ===
							highlightedIndex && highlightedIndex >= 0
							? 'bg-white/10'
							: 'bg-transparent hover:bg-white/7'}"
						onmouseenter={() => onHighlight(index)}
						onclick={() => onSelect(suggestion)}
					>
						<div
							class="rounded-pill flex h-9 w-9 shrink-0 items-center justify-center bg-white/8 text-white/85"
						>
							<Icon class="h-5 w-5" strokeWidth="2" />
						</div>
						<div class="min-w-0">
							<div class="truncate text-sm font-semibold text-white/90">
								{suggestion.title}
							</div>
							{#if suggestion.subtitle}
								<div class="truncate text-sm text-white/55">
									{suggestion.subtitle}
								</div>
							{/if}
						</div>
					</button>
				{/each}
			</div>
		</div>
	</LiquidGlass>
{/if}
