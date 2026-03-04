<script lang="ts">
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { device } from '$lib/stores/device.svelte'
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
	let searchQuery = $state('')
	let searchInputEl: HTMLInputElement | null = $state(null)

	const currentAgent = $derived(
		agents.list.length === 0
			? null
			: agents.list.find((agent) => agent.id === selectedAgent) || agents.list[0]
	)

	const filteredAgents = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase()
		if (!q) return agents.list
		return agents.list.filter(
			(a) =>
				a.name.toLowerCase().includes(q) ||
				(a.description ?? '').toLowerCase().includes(q) ||
				((a as { tags?: string[] }).tags ?? []).some((t) => t.toLowerCase().includes(q))
		)
	})

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

	// focus search input when menu opens (desktop only - avoid forcing keyboard on mobile)
	$effect(() => {
		if (isOpen) {
			searchQuery = ''
			if (!device.isMobile) {
				requestAnimationFrame(() => searchInputEl?.focus())
			}
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
		class="rounded-container min-w-80"
		estimatedHeight={380}
	>
		<!-- search -->
		<div class="flex items-center gap-2 px-3 pt-2 pb-3">
			<Search class="text-foreground/40 h-4 w-4 shrink-0" />
			<input
				bind:this={searchInputEl}
				bind:value={searchQuery}
				type="text"
				placeholder="search an agent"
				class="text-foreground/90 placeholder:text-foreground/40 min-w-0 flex-1 bg-transparent py-1.5 text-sm outline-none"
			/>
		</div>

		<ul class="m-0 list-none p-0" role="listbox">
			{#if filteredAgents.length === 0}
				<li class="text-foreground/50 px-3 py-3 text-center text-sm">no agents found</li>
			{:else}
				{#each filteredAgents as agent (agent.id)}
					{@const isSelected = agent.id === selectedAgent}
					{@const tags = (agent as { tags?: string[] }).tags ?? []}
					<li role="option" aria-selected={isSelected}>
						<button
							class="rounded-pill hover:bg-foreground/8 flex w-full cursor-pointer items-center gap-3 border-none bg-transparent px-3 py-2.5 text-left transition-all duration-150 {isSelected
								? 'ring-foreground/20 ring-1'
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
									class="bg-foreground/10 text-foreground/80 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold uppercase"
								>
									{agent.name.charAt(0)}
								</div>
							{/if}

							<div class="flex min-w-0 flex-1 flex-col items-start gap-1">
								<span class="text-foreground/95 text-[0.9375rem] font-semibold"
									>{agent.name}</span
								>
								{#if tags.length > 0}
									<div class="flex flex-wrap gap-1">
										{#each tags as tag (tag)}
											<span
												class="bg-foreground/8 text-foreground/60 rounded-full px-1.5 py-0.5 text-[0.6875rem] font-medium"
											>
												{tag}
											</span>
										{/each}
									</div>
								{/if}
							</div>
							{#if isSelected}
								<Check
									class="text-foreground/80 h-4 w-4 shrink-0"
									strokeWidth="2.5"
								/>
							{/if}
						</button>
					</li>
				{/each}
			{/if}
		</ul>
	</PopupMenu>
</div>
