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
				? 'border-foreground/20 bg-foreground/12 text-foreground'
				: 'border-foreground/10 bg-foreground/5 text-foreground/60 hover:border-foreground/15 hover:bg-foreground/8 hover:text-foreground'}"
		>
			<!-- radio dot indicator -->
			<span
				class="flex h-4 w-4 items-center justify-center rounded-full border-2 transition-all
					{isSelected ? 'border-foreground' : 'border-foreground/40'}"
			>
				{#if isSelected}
					<span class="bg-foreground h-2 w-2 rounded-full"></span>
				{/if}
			</span>
			<span>{option.label}</span>
		</button>
	{/each}
</div>
