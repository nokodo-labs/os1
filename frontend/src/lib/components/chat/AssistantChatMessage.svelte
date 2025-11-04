<script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
        content: string
        timestamp?: Date
        actions?: Snippet
        isLastMessage?: boolean
    }

    let { content, timestamp, actions, isLastMessage = false }: Props = $props()

    let showActions = $state(false)

    function handleMouseEnter() {
        showActions = true
    }

    function handleMouseLeave() {
        showActions = false
    }
</script>

<div
    class="flex w-full animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] flex-col items-start gap-3 self-start"
    onmouseenter={handleMouseEnter}
    onmouseleave={handleMouseLeave}
>
    <div class="relative w-full px-2 py-1">
        <div
            class="text-[0.95rem] leading-relaxed wrap-break-word text-white [text-shadow:0_2px_20px_rgba(0,0,0,0.8)]"
        >
            {content}
        </div>
        {#if timestamp}
            <div class="mt-2 text-xs text-white/40">
                {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </div>
        {/if}
    </div>

    {#if actions}
        <div
            class="flex gap-1.5 px-1 transition-opacity duration-200 {isLastMessage || showActions
                ? 'opacity-100'
                : 'opacity-0'}"
        >
            {@render actions()}
        </div>
    {/if}
</div>

<style>
    @keyframes messageSlideIn {
        from {
            opacity: 0;
            transform: translateY(10px) scale(0.98);
        }
        to {
            opacity: 1;
            transform: translateY(0) scale(1);
        }
    }
</style>
