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

<div class="model-selector">
    <button class="selector-trigger liquid-glass" onclick={toggleDropdown}>
        <div class="model-info">
            <span class="model-name">{selectedModel?.name}</span>
            <span class="model-provider">{selectedModel?.provider}</span>
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
            class="chevron"
            class:open={isOpen}
        >
            <path d="m6 9 6 6 6-6" />
        </svg>
    </button>

    {#if isOpen}
        <div class="dropdown liquid-glass">
            {#each models as model}
                <button
                    class="dropdown-item"
                    class:selected={model.id === selected}
                    onclick={() => selectModel(model.id)}
                >
                    <div class="model-info">
                        <span class="model-name">{model.name}</span>
                        <span class="model-provider">{model.provider}</span>
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
    .model-selector {
        position: relative;
    }

    .selector-trigger {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 0.5rem 1rem;
        border: none;
        border-radius: 0.75rem;
        backdrop-filter: blur(10px);
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.15), rgba(255, 255, 255, 0.05));
        cursor: pointer;
        transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        min-width: 180px;
    }

    .selector-trigger:hover {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.1));
        transform: translateY(-2px);
    }

    .model-info {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        flex: 1;
    }

    .model-name {
        font-size: 0.9375rem;
        font-weight: 500;
        color: rgba(255, 255, 255, 0.95);
    }

    .model-provider {
        font-size: 0.75rem;
        color: rgba(255, 255, 255, 0.5);
    }

    .chevron {
        transition: transform 0.3s ease;
        color: rgba(255, 255, 255, 0.6);
    }

    .chevron.open {
        transform: rotate(180deg);
    }

    .dropdown {
        position: absolute;
        top: calc(100% + 0.5rem);
        right: 0;
        min-width: 220px;
        padding: 0.5rem;
        border-radius: 0.75rem;
        backdrop-filter: blur(20px) saturate(180%);
        background: linear-gradient(135deg, rgba(30, 30, 40, 0.95), rgba(20, 20, 30, 0.95));
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        z-index: 100;
        animation: dropdownSlide 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
    }

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

    .dropdown-item {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        width: 100%;
        padding: 0.75rem;
        border: none;
        border-radius: 0.5rem;
        background: transparent;
        cursor: pointer;
        transition: all 0.2s ease;
        text-align: left;
    }

    .dropdown-item:hover {
        background: rgba(255, 255, 255, 0.1);
    }

    .dropdown-item.selected {
        background: linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(99, 102, 241, 0.2));
    }

    .dropdown-item .model-info {
        flex: 1;
    }
</style>
