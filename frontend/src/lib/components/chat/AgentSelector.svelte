<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { selectedAgent as selectedAgentStore } from '$lib/stores/selectedAgent.svelte'

	interface Props {
		selectedAgent: string
		onAgentChange: (agentId: string) => void
	}

	let { selectedAgent, onAgentChange }: Props = $props()

	let isOpen = $state(false)
	let didLoadAgents = $state(false)
	let didAutoSelect = $state(false)
	let anchorEl = $state<HTMLElement | null>(null)

	const currentAgent = $derived(
		agents.list.length === 0
			? null
			: agents.list.find((agent) => agent.id === selectedAgent) || agents.list[0]
	)

	$effect(() => {
		if (didLoadAgents) return
		didLoadAgents = true
		void agents.load()
	})

	$effect(() => {
		if (didAutoSelect) return
		if (agents.list.length === 0) return
		const hasSelected = selectedAgent && agents.list.some((agent) => agent.id === selectedAgent)
		if (!hasSelected) {
			didAutoSelect = true
			onAgentChange(selectedAgentStore.resolveDefault(agents.list))
		}
	})

	function toggle() {
		if (agents.list.length === 0) return
		isOpen = !isOpen
	}

	function select(agentId: string) {
		isOpen = false
		onAgentChange(agentId)
	}

	function closeMenu() {
		isOpen = false
	}
</script>

<div class="agent-selector relative flex items-center pl-1">
	<button
		bind:this={anchorEl}
		class="flex cursor-pointer items-center gap-1 border-none bg-transparent transition-transform duration-300 hover:scale-[1.05] active:scale-[0.97]"
		onclick={toggle}
		aria-expanded={isOpen}
		aria-haspopup="listbox"
	>
		<span
			class="min-w-0 truncate bg-clip-text text-xl font-semibold whitespace-nowrap text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
			style="background-image: linear-gradient(to bottom right, var(--accent-primary), var(--accent-primary));"
		>
			{currentAgent?.name ?? 'assistant'}
		</span>
		<span style="color: var(--accent-primary);">
			<ChevronDown
				class="h-4 w-4 transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
				strokeWidth="2"
			/>
		</span>
	</button>

	<PopupMenu
		open={isOpen}
		{anchorEl}
		onClose={closeMenu}
		class="rounded-container min-w-72"
		estimatedHeight={320}
	>
		<ul class="m-0 list-none p-0" role="listbox">
			{#each agents.list as agent (agent.id)}
				{@const isSelected = agent.id === selectedAgent}
				<li role="option" aria-selected={isSelected}>
					<button
						class="rounded-pill flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2.5 text-left transition-all duration-150 hover:bg-foreground/8 {isSelected
							? 'ring-1 ring-foreground/20'
							: ''}"
						style={isSelected ? 'background-color: var(--accent-bg);' : ''}
						onclick={() => select(agent.id)}
					>
						{#if agent.profile_image_url}
							<img
								src={agent.profile_image_url}
								alt={agent.name}
								class="h-8 w-8 shrink-0 rounded-full object-cover"
							/>
						{:else}
							<div
								class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-foreground/10 text-sm font-semibold text-foreground/80 uppercase"
							>
								{agent.name.charAt(0)}
							</div>
						{/if}

						<div class="flex min-w-0 flex-1 flex-col items-start gap-1">
							<span class="text-[0.9375rem] font-semibold text-foreground/95"
								>{agent.name}</span
							>
						</div>
						{#if isSelected}
							<Check class="h-4 w-4 shrink-0 text-foreground/80" strokeWidth="2.5" />
						{/if}
					</button>
				</li>
			{/each}
		</ul>
	</PopupMenu>
</div>
