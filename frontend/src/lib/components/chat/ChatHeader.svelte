<script lang="ts">
    import ChevronDown from '$lib/components/icons/ChevronDown.svelte'

    interface Agent {
        id: string
        name: string
        description?: string
    }

    interface Props {
        selectedAgent?: string
        onAgentChange?: (agentId: string) => void
    }

    let { selectedAgent = 'gpt-4', onAgentChange }: Props = $props()

    // Mock agent data
    const agents: Agent[] = [
        { id: 'gpt-4', name: 'GPT-4', description: 'most capable model' },
        { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', description: 'faster, optimized' },
        { id: 'claude-3-opus', name: 'Claude 3 Opus', description: "anthropic's flagship" },
        { id: 'claude-3-sonnet', name: 'Claude 3 Sonnet', description: 'balanced performance' },
        { id: 'gemini-pro', name: 'Gemini Pro', description: "google's advanced model" },
        { id: 'llama-3', name: 'Llama 3', description: 'open source powerhouse' },
    ]

    let isDropdownOpen = $state(false)
    let currentAgent = $derived(agents.find((a) => a.id === selectedAgent) || agents[0])

    function toggleDropdown() {
        isDropdownOpen = !isDropdownOpen
    }

    function selectAgent(agentId: string) {
        isDropdownOpen = false
        onAgentChange?.(agentId)
    }

    function handleClickOutside(event: MouseEvent) {
        const target = event.target as HTMLElement
        if (!target.closest('.agent-selector')) {
            isDropdownOpen = false
        }
    }

    $effect(() => {
        if (isDropdownOpen) {
            document.addEventListener('click', handleClickOutside)
            return () => document.removeEventListener('click', handleClickOutside)
        }
    })
</script>

<header
    class="liquid-glass mt-5 mb-0 rounded-full px-7 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.45)]"
>
    <span class="liquid-glass__highlight" aria-hidden="true"></span>

    <div class="liquid-glass__content relative flex items-center justify-start">
        <div class="relative">
            <button
                class="flex cursor-pointer items-center gap-2 rounded-2xl border-none bg-transparent px-4 py-2 transition-all duration-200 hover:bg-white/5 active:scale-[0.98]"
                onclick={toggleDropdown}
                aria-expanded={isDropdownOpen}
                aria-haspopup="listbox"
            >
                <span
                    class="bg-linear-to-br from-[#cdbdff] to-[#7c83ff] bg-clip-text text-xl font-semibold text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
                    >{currentAgent.name}</span
                >
                <ChevronDown
                    className="text-[rgba(205,189,255,0.7)] transition-transform duration-200 w-4 h-4 {isDropdownOpen
                        ? 'rotate-180'
                        : ''}"
                    strokeWidth="2"
                />
            </button>

            {#if isDropdownOpen}
                <div
                    class="liquid-glass absolute top-[calc(100%+0.5rem)] left-1/2 z-1000 min-w-64 -translate-x-1/2 animate-[dropdown-appear_0.2s_ease] rounded-3xl p-2 shadow-[0_24px_48px_rgba(12,10,30,0.5)]"
                >
                    <span class="liquid-glass__highlight" aria-hidden="true"></span>
                    <ul class="liquid-glass__content m-0 list-none p-0" role="listbox">
                        {#each agents as agent (agent.id)}
                            <li role="option" aria-selected={agent.id === selectedAgent}>
                                <button
                                    class="flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-2xl border-none bg-transparent px-4 py-3 text-left transition-all duration-150 hover:bg-white/8"
                                    class:!bg-[rgba(124,131,255,0.15)]={agent.id === selectedAgent}
                                    class:hover:!bg-[rgba(124,131,255,0.2)]={agent.id ===
                                        selectedAgent}
                                    onclick={() => selectAgent(agent.id)}
                                >
                                    <span class="text-[0.9375rem] font-semibold text-white/95"
                                        >{agent.name}</span
                                    >
                                    {#if agent.description}
                                        <span class="text-[0.8125rem] text-[rgba(225,225,255,0.6)]"
                                            >{agent.description}</span
                                        >
                                    {/if}
                                </button>
                            </li>
                        {/each}
                    </ul>
                </div>
            {/if}
        </div>
    </div>
</header>

<style>
    @keyframes dropdown-appear {
        from {
            opacity: 0;
            transform: translateX(-50%) translateY(-0.5rem);
        }
        to {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }
    }
</style>
