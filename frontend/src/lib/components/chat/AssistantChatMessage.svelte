<script lang="ts">
    import type { Snippet } from 'svelte'

    interface Props {
        content: string
        timestamp?: Date
        actions?: Snippet
        isLastMessage?: boolean
        modelName?: string
    }

    let {
        content,
        timestamp,
        actions,
        isLastMessage = false,
        modelName = 'Assistant',
    }: Props = $props()

    let showActions = $state(false)
    let isHovered = $state(false)

    function handleMouseEnter() {
        showActions = true
        isHovered = true
    }

    function handleMouseLeave() {
        showActions = false
        isHovered = false
    }
</script>

<div
    class="flex w-full animate-[messageSlideIn_0.3s_cubic-bezier(0.34,1.56,0.64,1)] items-start gap-3 self-start"
    onmouseenter={handleMouseEnter}
    onmouseleave={handleMouseLeave}
    role="article"
>
    <!-- Avatar on the left -->
    <div
        class="mt-1 h-10 w-10 shrink-0 rounded-full bg-purple-500 shadow-lg shadow-purple-500/50"
    ></div>

    <!-- Content container -->
    <div class="relative flex min-w-0 flex-1 flex-col gap-2">
        <!-- Header with model name and timestamp -->
        <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-white/90">{modelName}</span>
            {#if timestamp}
                <span
                    class="text-xs text-white/40 transition-opacity duration-200 {isHovered
                        ? 'opacity-100'
                        : 'opacity-0'}"
                >
                    {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
            {/if}
        </div>

        <!-- Message content -->
        <div
            class="text-[0.95rem] leading-relaxed wrap-break-word text-white [text-shadow:0_2px_20px_rgba(0,0,0,0.8)]"
        >
            {content}
        </div>

        <!-- Actions -->
        {#if actions}
            <div
                class="flex gap-1.5 transition-opacity duration-200 {isLastMessage || showActions
                    ? 'opacity-100'
                    : 'opacity-0'}"
            >
                {@render actions()}
            </div>
        {/if}
    </div>
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
