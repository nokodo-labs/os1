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

	const gridClass = $derived(columns === 'two' ? 'sm:grid-cols-2' : 'grid-cols-1')

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

<div class="grid gap-2 {gridClass} {className}" role="radiogroup" aria-label={ariaLabel}>
	{#each options as option (option.value)}
		{@const isSelected = option.value === value}
		{@const iconUrl = activeIconUrl(option)}
		<button
			type="button"
			role="radio"
			aria-checked={isSelected}
			disabled={disabled || option.disabled}
			onclick={() => select(option)}
			class="rounded-container border-foreground/10 bg-foreground/4 hover:border-foreground/18 hover:bg-foreground/7 flex w-full cursor-pointer items-start gap-3 border p-3 text-left transition-all duration-150 disabled:pointer-events-none disabled:opacity-45 {isSelected
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
			<span class="min-w-0 flex-1">
				<span class="text-foreground/90 block text-sm font-semibold">{option.label}</span>
				{#if option.description}
					<span class="text-foreground/52 mt-0.5 block text-xs leading-relaxed">
						{option.description}
					</span>
				{/if}
			</span>
			<span
				class="rounded-pill border-foreground/12 flex h-6 w-6 shrink-0 items-center justify-center border {isSelected
					? 'bg-foreground text-background'
					: 'bg-foreground/4 text-transparent'}"
			>
				<Check class="h-3.5 w-3.5" />
			</span>
		</button>
	{/each}
</div>
