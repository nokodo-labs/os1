<script lang="ts">
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

<div class="flex gap-2 {className}">
	{#each options as option (option.value)}
		{@const isSelected = value === option.value}
		<button
			type="button"
			onclick={() => onchange(option.value)}
			class="rounded-pill flex flex-1 cursor-pointer items-center justify-center gap-2.5 border px-4 py-2.5 text-sm font-medium transition-all duration-200
				{isSelected
				? 'border-white/20 bg-white/12 text-white'
				: 'border-white/10 bg-white/5 text-white/60 hover:border-white/15 hover:bg-white/8 hover:text-white'}"
		>
			<!-- radio dot indicator -->
			<span
				class="flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all
					{isSelected ? 'border-white' : 'border-white/40'}"
			>
				{#if isSelected}
					<span class="h-2 w-2 rounded-full bg-white"></span>
				{/if}
			</span>
			<span>{option.label}</span>
		</button>
	{/each}
</div>
