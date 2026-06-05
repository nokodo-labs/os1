<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'

	export type DropdownSelectOption = {
		value: string
		label: string
		description?: string
		disabled?: boolean
	}

	interface Props {
		options: readonly DropdownSelectOption[]
		value: string
		onchange: (value: string) => void
		placeholder?: string
		disabled?: boolean
		ariaLabel?: string
		class?: string
		buttonClass?: string
	}

	let {
		options,
		value,
		onchange,
		placeholder = 'select',
		disabled = false,
		ariaLabel = 'select an option',
		class: className = '',
		buttonClass = '',
	}: Props = $props()

	let open = $state(false)

	const selectedOption = $derived(options.find((option) => option.value === value) ?? null)

	function choose(option: DropdownSelectOption): void {
		if (disabled || option.disabled) return
		onchange(option.value)
		open = false
	}
</script>

<div class="relative {className}">
	<button
		type="button"
		aria-label={ariaLabel}
		aria-expanded={open}
		{disabled}
		onclick={() => (open = !open)}
		class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 hover:bg-foreground/8 focus:border-foreground/20 focus:bg-foreground/8 flex w-full cursor-pointer items-center justify-between gap-3 border px-4 py-2.5 text-left text-sm transition-colors outline-none disabled:pointer-events-none disabled:opacity-45 {buttonClass}"
	>
		<span class="min-w-0 flex-1 truncate">{selectedOption?.label ?? placeholder}</span>
		<ChevronDown class="text-foreground/50 h-4 w-4 shrink-0" />
	</button>
	{#if open}
		<div
			class="rounded-popup border-foreground/12 bg-background/95 shadow-soft absolute z-20 mt-2 w-full border p-1 backdrop-blur-xl"
		>
			{#each options as option (option.value)}
				{@const isSelected = option.value === value}
				<button
					type="button"
					disabled={disabled || option.disabled}
					class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors disabled:pointer-events-none disabled:opacity-45 {isSelected
						? 'bg-foreground/10 text-foreground'
						: 'text-foreground/75'}"
					onclick={() => choose(option)}
				>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-sm font-medium">{option.label}</span>
						{#if option.description}
							<span class="text-foreground/48 mt-0.5 block truncate text-xs">
								{option.description}
							</span>
						{/if}
					</span>
					{#if isSelected}
						<Check class="h-4 w-4 shrink-0" />
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	button {
		-webkit-tap-highlight-color: transparent;
	}
</style>
