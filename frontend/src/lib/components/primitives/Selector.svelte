<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'

	export type SelectorOption = {
		value: string
		label: string
		description?: string
		iconUrl?: string
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

	function markIconFailed(value: string) {
		if (failedIcons.includes(value)) return
		failedIcons = [...failedIcons, value]
	}
</script>

<div class="grid gap-2 {gridClass} {className}" role="radiogroup" aria-label={ariaLabel}>
	{#each options as option (option.value)}
		{@const isSelected = option.value === value}
		{@const showIcon = option.iconUrl && !failedIcons.includes(option.value)}
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
				{#if showIcon}
					<img
						src={option.iconUrl}
						alt=""
						class="h-6 w-6 object-contain"
						onerror={() => markIconFailed(option.value)}
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
