<script lang="ts">
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import { RadioGroup } from '$lib/components/primitives'
	import { quintOut } from 'svelte/easing'
	import { slide } from 'svelte/transition'
	import type { ExportOptionDefinition, ExportOptionsBinding } from './exportOptions'

	interface Props {
		binding: ExportOptionsBinding
	}

	let { binding }: Props = $props()

	let isOpen = $state(false)

	function choicesOf(definition: ExportOptionDefinition) {
		return definition.choices.map((choice) => ({
			value: choice.id,
			label: choice.label,
			icon: choice.icon,
		}))
	}
</script>

<div class="border-foreground/10 mt-1 border-t pt-3">
	<button
		type="button"
		class="text-foreground/70 hover:text-foreground flex w-full cursor-pointer items-center gap-2 bg-transparent text-left transition-colors duration-150"
		aria-expanded={isOpen}
		onclick={() => (isOpen = !isOpen)}
	>
		<AdjustmentsHorizontal class="h-4 w-4 shrink-0" />
		<span class="text-sm font-medium">options</span>
		<ChevronDown
			class="ml-auto h-4 w-4 shrink-0 transition-transform duration-200 {isOpen
				? 'rotate-180'
				: ''}"
		/>
	</button>

	{#if isOpen}
		<div class="grid gap-3 pt-3" transition:slide={{ duration: 220, easing: quintOut }}>
			{#each binding.definitions as definition (definition.id)}
				{@const Icon = definition.icon}
				<div class="grid min-w-0 gap-2">
					<div class="text-foreground/50 flex items-center gap-1.5">
						<Icon class="h-3.5 w-3.5 shrink-0" />
						<span class="text-xs font-medium">{definition.label}</span>
					</div>
					<RadioGroup
						options={choicesOf(definition)}
						value={definition.read(binding.values)}
						onchange={(choice) => binding.onchange(definition, choice)}
					/>
				</div>
			{/each}
		</div>
	{/if}
</div>
