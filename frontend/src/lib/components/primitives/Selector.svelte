<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'

	export type SelectorOption = {
		value: string
		label: string
		description?: string
		iconUrl?: string
		iconUrls?: readonly string[]
		disabled?: boolean
	}

	interface Props {
		options: readonly SelectorOption[]
		value: string
		onchange: (value: string) => void
		columns?: 'one' | 'two'
		disabled?: boolean
		ariaLabel?: string
		class?: string
	}

	let {
		options,
		value,
		onchange,
		columns = 'one',
		disabled = false,
		ariaLabel = 'select an option',
		class: className = '',
	}: Props = $props()

	let failedIcons = $state<string[]>([])

	// container queries, not viewport ones: a selector in a narrow panel or modal has to
	// reflow even on a wide screen. two columns only once the container can hold them.
	const gridClass = $derived(columns === 'two' ? '@min-[30rem]/selector:grid-cols-2' : '')

	function select(option: SelectorOption) {
		if (disabled || option.disabled) return
		onchange(option.value)
	}

	function optionIconUrls(option: SelectorOption): readonly string[] {
		if (option.iconUrls && option.iconUrls.length > 0) return option.iconUrls
		return option.iconUrl ? [option.iconUrl] : []
	}

	function iconFailureKey(value: string, url: string): string {
		return `${value}:${url}`
	}

	function activeIconUrl(option: SelectorOption): string | undefined {
		return optionIconUrls(option).find(
			(url) => !failedIcons.includes(iconFailureKey(option.value, url))
		)
	}

	function markIconFailed(value: string, url: string) {
		const key = iconFailureKey(value, url)
		if (failedIcons.includes(key)) return
		failedIcons = [...failedIcons, key]
	}
</script>

<div class="@container/selector {className}">
	<div class="grid grid-cols-1 gap-2 {gridClass}" role="radiogroup" aria-label={ariaLabel}>
		{#each options as option (option.value)}
			{@const isSelected = option.value === value}
			{@const iconUrl = activeIconUrl(option)}
			<button
				type="button"
				role="radio"
				aria-checked={isSelected}
				disabled={disabled || option.disabled}
				onclick={() => select(option)}
				class="rounded-container border-foreground/10 bg-foreground/4 hover:border-foreground/18 hover:bg-foreground/7 flex w-full min-w-0 cursor-pointer flex-wrap items-start gap-3 border p-3 text-left transition-all duration-150 disabled:pointer-events-none disabled:opacity-45 {isSelected
					? 'border-foreground/24 bg-foreground/10 text-foreground shadow-[0_0_0_1px_color-mix(in_oklch,var(--foreground)_12%,transparent)]'
					: 'text-foreground/75'}"
			>
				<span class="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden">
					{#if iconUrl}
						<img
							src={iconUrl}
							alt=""
							class="h-6 w-6 object-contain"
							onerror={() => markIconFailed(option.value, iconUrl)}
						/>
					{:else}
						<GlobeAlt class="text-foreground/55 h-5 w-5" />
					{/if}
				</span>
				<!-- too narrow for a row: the label wraps under the icon instead of overflowing -->
				<span
					class="@min-[13rem]/selector:order-none @min-[13rem]/selector:flex-1 @min-[13rem]/selector:basis-auto order-last min-w-0 basis-full break-words"
				>
					<span class="text-foreground/90 block text-sm font-semibold"
						>{option.label}</span
					>
					{#if option.description}
						<span class="text-foreground/52 mt-0.5 block text-xs leading-relaxed">
							{option.description}
						</span>
					{/if}
				</span>
				<span
					class="rounded-pill border-foreground/12 ml-auto flex h-6 w-6 shrink-0 items-center justify-center border {isSelected
						? 'bg-foreground text-background'
						: 'bg-foreground/4 text-transparent'}"
				>
					<Check class="h-3.5 w-3.5" />
				</span>
			</button>
		{/each}
	</div>
</div>
