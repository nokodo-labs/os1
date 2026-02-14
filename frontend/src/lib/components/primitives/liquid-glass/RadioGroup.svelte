<script lang="ts">
	import LiquidGlass from '$lib/components/effects/LiquidGlass.svelte'

	type Option<T extends string> = {
		value: T
		label: string
	}

	interface RadioGroupProps<T extends string> {
		options: readonly Option<T>[]
		value: T
		onchange: (value: T) => void
		class?: string
	}

	let { options, value, onchange, class: className = '' }: RadioGroupProps<string> = $props()
</script>

<div class="flex gap-2 {className}" role="radiogroup">
	{#each options as option (option.value)}
		{@const isSelected = value === option.value}
		<LiquidGlass
			tag="button"
			type="button"
			role="radio"
			aria-checked={isSelected}
			onclick={() => onchange(option.value)}
			class="rounded-pill flex flex-1 cursor-pointer items-center justify-center gap-2.5 border px-4 py-2.5 text-sm font-medium
				transition-[transform,box-shadow,ring-color,background-color,color] duration-300
				ease-in-out hover:scale-[1.06] active:scale-[1.1]
				{isSelected
				? 'border-white/25 bg-white/14 text-white shadow-[0_14px_30px_rgba(12,10,30,0.25)]'
				: 'border-white/10 bg-white/6 text-white/60 hover:border-white/18 hover:bg-white/10 hover:text-white'}"
		>
			<span
				class="flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all
					{isSelected ? 'border-white' : 'border-white/40'}"
			>
				{#if isSelected}
					<span class="h-2 w-2 rounded-full bg-white"></span>
				{/if}
			</span>
			<span>{option.label}</span>
		</LiquidGlass>
	{/each}
</div>
