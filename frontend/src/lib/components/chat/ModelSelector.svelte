<script lang="ts">
	import { scale } from 'svelte/transition'

	interface Model {
		id: string
		name: string
		provider: string
	}

	interface Props {
		models: Model[]
		selected: string
		onSelect: (modelId: string) => void
	}

	let { models, selected, onSelect }: Props = $props()

	let isOpen = $state(false)

	const selectedModel = $derived(models.find((m) => m.id === selected) || models[0])

	function toggleDropdown() {
		isOpen = !isOpen
	}

	function selectModel(modelId: string) {
		onSelect(modelId)
		isOpen = false
	}
</script>

<div class="relative">
	<button
		class="liquid-glass rounded-container from-foreground/15 to-foreground/5 hover:from-foreground/20 hover:to-foreground/10 flex min-w-45 cursor-pointer items-center gap-3 border-none bg-linear-to-br px-4 py-2 backdrop-blur-[10px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:-translate-y-0.5"
		onclick={toggleDropdown}
	>
		<div class="flex flex-1 flex-col items-start">
			<span class="text-foreground/95 text-[0.9375rem] font-medium"
				>{selectedModel?.name}</span
			>
			<span class="text-foreground/50 text-xs">{selectedModel?.provider}</span>
		</div>
		<svg
			width="16"
			height="16"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
			stroke-linecap="round"
			stroke-linejoin="round"
			class="text-foreground/60 transition-transform duration-300"
			class:rotate-180={isOpen}
		>
			<path d="m6 9 6 6 6-6" />
		</svg>
	</button>

	{#if isOpen}
		<div
			transition:scale={{ duration: 180, start: 0.96, opacity: 0 }}
			class="animate-popup-right liquid-glass rounded-container border-foreground/10 bg-popover/95 absolute top-[calc(100%+0.5rem)] right-0 z-100 min-w-55 border p-2 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-[20px] [backdrop-saturate:180%]"
		>
			{#each models as model (model.id)}
				<button
					class="rounded-pill hover:bg-foreground/10 flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-3 text-left transition-all duration-200"
					class:!bg-linear-to-br={model.id === selected}
					class:!from-[rgba(139,92,246,0.3)]={model.id === selected}
					class:!to-[rgba(99,102,241,0.2)]={model.id === selected}
					onclick={() => selectModel(model.id)}
				>
					<div class="flex flex-1 flex-col items-start">
						<span class="text-foreground/95 text-[0.9375rem] font-medium"
							>{model.name}</span
						>
						<span class="text-foreground/50 text-xs">{model.provider}</span>
					</div>
					{#if model.id === selected}
						<svg
							width="16"
							height="16"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<path d="M20 6 9 17l-5-5" />
						</svg>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
