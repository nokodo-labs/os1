<script lang="ts">
	import AgentAvatar from '$lib/components/chat/AgentAvatar.svelte'
	import EmptyState from '$lib/components/EmptyState.svelte'
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte'
	import Search from '$lib/components/icons/Search.svelte'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import PopupMenu from '$lib/components/primitives/PopupMenu.svelte'
	import { agents } from '$lib/stores/agents.svelte'
	import { device } from '$lib/stores/device.svelte'
	import { selectedAgent as selectedAgentStore } from '$lib/stores/selectedAgent.svelte'
	import { session } from '$lib/stores/session.svelte'

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
		if (!session.isLoggedIn) {
			didLoadAgents = false
			return
		}
		// reload when agents list was emptied by invalidation
		if (agents.list.length > 0 && didLoadAgents) return
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
				searchInputEl?.focus()
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

<div class="agent-selector relative flex min-w-0 flex-1 items-center pl-1">
	<button
		bind:this={anchorEl}
		class="flex min-w-0 cursor-pointer items-center gap-1 border-none bg-transparent transition-transform duration-300 hover:scale-[1.05] active:scale-[0.97]"
		onclick={toggle}
		aria-expanded={isOpen}
		aria-haspopup="menu"
	>
		<span
			class="min-w-0 truncate bg-clip-text text-xl font-semibold whitespace-nowrap text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
			style="background-image: linear-gradient(to bottom right, {agents.error
				? 'var(--color-error, #ef4444)'
				: 'var(--accent-primary)'}, {agents.error
				? 'var(--color-error, #ef4444)'
				: 'var(--accent-primary)'});"
			title={agents.error ?? ''}
		>
			{agents.error ? 'error' : (currentAgent?.name ?? 'select agent')}
		</span>
		<span class="shrink-0" style="color: var(--accent-primary);">
			<ChevronDown
				class="h-4 w-4 transition-transform duration-200 {isOpen ? 'rotate-180' : ''}"
				strokeWidth="2"
			/>
		</span>
	</button>

	<PopupMenu open={isOpen} {anchorEl} onClose={closeMenu} class="min-w-80" estimatedHeight={380}>
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

		{#if filteredAgents.length === 0}
			<EmptyState label="no agents found" compact />
		{:else}
			{#each filteredAgents as agent (agent.id)}
				{@const tags = (agent as { tags?: string[] }).tags ?? []}
				<MenuItem selected={agent.id === selectedAgent} onclick={() => select(agent.id)}>
					{#snippet iconSnippet()}
						<AgentAvatar
							name={agent.name}
							avatarUrl={agent.profile_image_url}
							class="size-full"
							textClass="text-xs"
						/>
					{/snippet}
					{agent.name}
					{#snippet detail()}
						{#if tags.length > 0}
							<span class="flex flex-wrap gap-1">
								{#each tags as tag (tag)}
									<span
										class="bg-foreground/8 text-foreground/60 rounded-full px-1.5 py-0.5 text-[0.6875rem] font-medium"
									>
										{tag}
									</span>
								{/each}
							</span>
						{/if}
					{/snippet}
				</MenuItem>
			{/each}
		{/if}
	</PopupMenu>
</div>
