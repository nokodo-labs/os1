<script lang="ts">
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
        class="liquid-glass flex min-w-[180px] cursor-pointer items-center gap-3 rounded-xl border-none bg-linear-to-br from-white/15 to-white/5 px-4 py-2 backdrop-blur-[10px] transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] hover:-translate-y-0.5 hover:from-white/20 hover:to-white/10"
        onclick={toggleDropdown}
    >
        <div class="flex flex-1 flex-col items-start">
            <span class="text-[0.9375rem] font-medium text-white/95">{selectedModel?.name}</span>
            <span class="text-xs text-white/50">{selectedModel?.provider}</span>
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
            class="text-white/60 transition-transform duration-300"
            class:rotate-180={isOpen}
        >
            <path d="m6 9 6 6 6-6" />
        </svg>
    </button>

    {#if isOpen}
        <div
            class="liquid-glass absolute top-[calc(100%+0.5rem)] right-0 z-100 min-w-[220px] animate-[dropdownSlide_0.2s_cubic-bezier(0.34,1.56,0.64,1)] rounded-xl border border-white/10 bg-linear-to-br from-[rgba(30,30,40,0.95)] to-[rgba(20,20,30,0.95)] p-2 shadow-[0_8px_32px_rgba(0,0,0,0.3)] backdrop-blur-[20px] [backdrop-saturate:180%]"
        >
            {#each models as model}
                <button
                    class="flex w-full cursor-pointer items-center gap-3 rounded-lg border-none bg-transparent px-3 py-3 text-left transition-all duration-200 hover:bg-white/10"
                    class:!bg-linear-to-br={model.id === selected}
                    class:!from-[rgba(139,92,246,0.3)]={model.id === selected}
                    class:!to-[rgba(99,102,241,0.2)]={model.id === selected}
                    onclick={() => selectModel(model.id)}
                >
                    <div class="flex flex-1 flex-col items-start">
                        <span class="text-[0.9375rem] font-medium text-white/95">{model.name}</span>
                        <span class="text-xs text-white/50">{model.provider}</span>
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

<style>
    @keyframes dropdownSlide {
        from {
            opacity: 0;
            transform: translateY(-10px) scale(0.95);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }
</style>
