<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import type { Component } from 'svelte'

	export type DropdownSelectOption = {
		value: string
		label: string
		description?: string
		disabled?: boolean
		icon?: Component
		iconVariant?: string
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
	let containerEl = $state<HTMLDivElement>()
	let buttonEl = $state<HTMLButtonElement>()
	let popupEl = $state<HTMLDivElement>()
	let pos = $state({ top: 0, left: 0, width: 0, maxHeight: 0, openUp: false })

	const selectedOption = $derived(options.find((option) => option.value === value) ?? null)

	function choose(option: DropdownSelectOption): void {
		if (disabled || option.disabled) return
		onchange(option.value)
		open = false
	}

	// the popup is portaled to <body> to escape ancestor stacking contexts (the
	// liquid-glass cards create one via backdrop-filter), so it is positioned
	// from the trigger's viewport rect instead of via absolute positioning.
	function updatePosition(): void {
		if (!buttonEl) return
		const rect = buttonEl.getBoundingClientRect()
		const gap = 8
		const spaceBelow = window.innerHeight - rect.bottom
		const spaceAbove = rect.top
		const openUp = spaceBelow < 240 && spaceAbove > spaceBelow
		const maxHeight = Math.max(120, (openUp ? spaceAbove : spaceBelow) - gap - 8)
		pos = {
			top: openUp ? rect.top - gap : rect.bottom + gap,
			left: rect.left,
			width: rect.width,
			maxHeight,
			openUp,
		}
	}

	function onOutsideClick(e: MouseEvent): void {
		const target = e.target as Node
		if (open && !containerEl?.contains(target) && !popupEl?.contains(target)) {
			open = false
		}
	}

	$effect(() => {
		if (!open) return
		updatePosition()
		const reposition = () => updatePosition()
		window.addEventListener('scroll', reposition, true)
		window.addEventListener('resize', reposition)
		document.addEventListener('click', onOutsideClick, true)
		return () => {
			window.removeEventListener('scroll', reposition, true)
			window.removeEventListener('resize', reposition)
			document.removeEventListener('click', onOutsideClick, true)
		}
	})
</script>

<div class="relative {className}" bind:this={containerEl}>
	<button
		type="button"
		aria-label={ariaLabel}
		aria-expanded={open}
		{disabled}
		bind:this={buttonEl}
		onclick={() => (open = !open)}
		class="rounded-pill border-foreground/10 bg-foreground/5 text-foreground/90 hover:bg-foreground/8 focus:border-foreground/20 focus:bg-foreground/8 flex w-full cursor-pointer items-center justify-between gap-2 border px-4 py-2.5 text-left text-sm transition-colors outline-none disabled:pointer-events-none disabled:opacity-45 {buttonClass}"
	>
		{#if selectedOption?.icon}
			{@const Icon = selectedOption.icon}
			<Icon
				variant={selectedOption.iconVariant}
				class="h-4 w-4 shrink-0 text-foreground/50"
			/>
		{/if}
		<span class="min-w-0 flex-1 truncate">{selectedOption?.label ?? placeholder}</span>
		<ChevronDown class="text-foreground/50 h-4 w-4 shrink-0" />
	</button>
	{#if open}
		<div
			use:portal
			bind:this={popupEl}
			class="rounded-popup border-foreground/12 bg-background/95 shadow-soft fixed z-100 overflow-auto border p-1 backdrop-blur-xl"
			style="top: {pos.top}px; left: {pos.left}px; width: {pos.width}px; max-height: {pos.maxHeight}px;{pos.openUp
				? ' transform: translateY(-100%);'
				: ''}"
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
					{#if option.icon}
						{@const Icon = option.icon}
						<Icon
							variant={option.iconVariant}
							class="h-4 w-4 shrink-0 text-foreground/50"
						/>
					{/if}
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
