<script lang="ts">
    import type { Snippet } from 'svelte'
    import { onDestroy, onMount } from 'svelte'
    import tippy, { type Instance, type Placement } from 'tippy.js'

    interface Props {
        content: string
        placement?: Placement
        className?: string
        children: Snippet
    }

    let { content, placement = 'top', className = '', children }: Props = $props()

    let tooltipElement: HTMLElement
    let tooltipInstance: Instance | null = null

    onMount(() => {
        if (tooltipElement && content) {
            tooltipInstance = tippy(tooltipElement, {
                content: content,
                placement: placement,
                arrow: false,
                offset: [0, 8],
                animation: 'scale',
                duration: [200, 150],
                theme: 'liquid-glass',
            })
        }
    })

    $effect(() => {
        if (tooltipInstance && content) {
            tooltipInstance.setContent(content)
        }
    })

    onDestroy(() => {
        if (tooltipInstance) {
            tooltipInstance.destroy()
        }
    })
</script>

<div bind:this={tooltipElement} class={className}>
    {@render children()}
</div>

<style>
    :global(.tippy-box[data-theme~='liquid-glass']) {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(3px);
        -webkit-backdrop-filter: blur(3px);
        border: 1px solid rgba(255, 255, 255, 0.35);
        border-radius: 8px;
        box-shadow:
            0px 6px 24px rgba(0, 0, 0, 0.2),
            inset 0 0 20px -5px rgba(255, 255, 255, 0.65);
        color: rgba(255, 255, 255, 0.95);
        font-size: 0.75rem;
        padding: 6px 10px;
        font-weight: 500;
        letter-spacing: 0.01em;
        isolation: isolate;
    }

    :global(.tippy-box[data-theme~='liquid-glass'] .tippy-content) {
        padding: 0;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
        position: relative;
        z-index: 3;
    }

    /* Fallback for browsers without backdrop-filter support */
    @supports not (backdrop-filter: blur(0)) {
        :global(.tippy-box[data-theme~='liquid-glass']) {
            background: rgba(22, 18, 36, 0.88);
        }
    }

    /* Subtle glow animation on show */
    :global(.tippy-box[data-theme~='liquid-glass'][data-state='visible']) {
        animation: tooltipGlow 0.2s ease-out;
    }

    @keyframes tooltipGlow {
        0% {
            box-shadow:
                0px 6px 24px rgba(0, 0, 0, 0.2),
                inset 0 0 0 rgba(255, 255, 255, 0);
        }
        100% {
            box-shadow:
                0px 6px 24px rgba(0, 0, 0, 0.2),
                inset 0 0 20px -5px rgba(255, 255, 255, 0.65);
        }
    }
</style>
