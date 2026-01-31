<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		selectedAgent: string
		onAgentChange: (agentId: string) => void
	}

	let { selectedAgent, onAgentChange }: Props = $props()

	let isOpen = $state(false)
	let didLoadAgents = $state(false)
	let didAutoSelect = $state(false)

	const currentAgent = $derived(
		agents.list.length === 0
			? null
			: agents.list.find((a) => a.id === selectedAgent) || agents.list[0]
	)

	$effect(() => {
		if (didLoadAgents) return
		didLoadAgents = true
		void agents.load()
	})

	$effect(() => {
		if (didAutoSelect) return
		if (agents.list.length === 0) return
		const hasSelected = selectedAgent && agents.list.some((a) => a.id === selectedAgent)
		if (!hasSelected) {
			didAutoSelect = true
			onAgentChange(agents.list[0].id)
		}
	})

	function handleClickOutside(event: MouseEvent) {
		const target = event.target as HTMLElement
		if (!target.closest('.agent-selector')) {
			isOpen = false
		}
	}

	function toggle() {
		if (agents.list.length === 0) return
		isOpen = !isOpen
	}

	function select(agentId: string) {
		isOpen = false
		onAgentChange(agentId)
	}

	$effect(() => {
		if (isOpen) {
			document.addEventListener('click', handleClickOutside)
			return () => document.removeEventListener('click', handleClickOutside)
		}
	})
</script>

<div class="agent-selector relative flex min-w-0 items-center gap-2">
	<button
		class="rounded-pill flex min-w-0 cursor-pointer items-center gap-2 border-none bg-transparent px-[clamp(8px,2.5vw,16px)] py-2 transition-all duration-200 hover:bg-white/5 active:scale-[0.98]"
		onclick={toggle}
		aria-expanded={isOpen}
		aria-haspopup="listbox"
	>
		<span
			class="min-w-0 truncate bg-clip-text text-xl font-semibold whitespace-nowrap text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
			style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
		>
			{currentAgent?.name ?? 'assistant'}
		</span>
		<span style="color: var(--accent-secondary);">
			<ChevronDown
				className="transition-transform duration-200 w-4 h-4 {isOpen ? 'rotate-180' : ''}"
				strokeWidth="2"
			/>
		</span>
	</button>

	{#if isOpen}
		<div
			transition:scale={{ duration: 180, start: 0.96, opacity: 0 }}
			class="animate-popup liquid-metal rounded-container z-1000 min-w-64 p-2 shadow-[0_24px_48px_rgba(12,10,30,0.5)]"
			style="position: absolute; top: calc(100% + 0.5rem); left: 0;"
		>
			<ul class="m-0 list-none p-0" role="listbox">
				{#each agents.list as agent (agent.id)}
					{@const isSelected = agent.id === selectedAgent}
					<li role="option" aria-selected={isSelected}>
						<button
							class="rounded-pill flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-4 py-3 text-left transition-all duration-150 hover:bg-white/8 {isSelected
								? 'ring-1 ring-white/20'
								: ''}"
							style={isSelected ? 'background-color: var(--accent-bg);' : ''}
							onclick={() => select(agent.id)}
						>
							<div class="flex min-w-0 flex-1 flex-col items-start gap-0.5">
								<span class="text-[0.9375rem] font-semibold text-white/95">
									{agent.name}
								</span>
								{#if agent.description}
									<span class="text-[0.8125rem] text-[rgba(225,225,255,0.6)]">
										{agent.description}
									</span>
								{/if}
							</div>
							{#if isSelected}
								<Check
									className="h-4 w-4 shrink-0 text-white/80"
									strokeWidth="2.5"
								/>
							{/if}
						</button>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>
