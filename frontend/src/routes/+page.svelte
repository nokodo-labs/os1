<script lang="ts">
    import { goto } from '$app/navigation'
    import { resolve } from '$app/paths'
    import ChatHeader from '$lib/components/chat/ChatHeader.svelte'
    import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
    import { fade } from 'svelte/transition'

    let inputValue = $state('')
    let isGenerating = $state(false)
    let selectedModel = $state('gpt-4')

    async function navigateToChat(threadId: string, content: string) {
        const url = `/chats/${threadId}?q=${encodeURIComponent(content)}`
        // Assume View Transitions API exists (per requirement), but keep a safe fallback.
        const start = (
            document as unknown as {
                startViewTransition?: (cb: () => Promise<void> | void) => void
            }
        ).startViewTransition
        if (start) {
            // Must be invoked with `document` as `this`.
            start.call(document, async () => {
                await goto(resolve(url as any), { keepFocus: true, noScroll: true })
            })
            return
        }
        await goto(resolve(url as any), { keepFocus: true, noScroll: true })
    }

    function handleSendMessage(content: string) {
        // Create a new thread ID (mock)
        const threadId = Date.now().toString()
        // Navigate to the chat page with a view transition
        void navigateToChat(threadId, content)
    }

    function handleStopGeneration() {
        isGenerating = false
    }
</script>

<!-- Scrollable Area (kept for layout parity with /chats/[id]) -->
<div class="flex-1 overflow-y-auto">
    <div class="mx-auto flex min-h-full w-full max-w-4xl flex-col px-8 pt-8 pb-32">
        <div style="view-transition-name: chat-header;">
            <ChatHeader
                selectedAgent={selectedModel}
                onAgentChange={(agentId: string) => (selectedModel = agentId)}
            ></ChatHeader>
        </div>
    </div>
</div>

<!-- Input Area (Fixed Bottom) -->
<div class="absolute right-0 bottom-0 left-0 z-10 pt-10 pb-8">
    <div class="mx-auto w-full max-w-4xl px-8">
        <div
            style="view-transition-name: chat-input;"
            class="-translate-y-[40vh] transition-all duration-500 ease-in-out"
        >
            <div
                style="view-transition-name: landing-greeting;"
                class="mb-8 flex flex-col items-center justify-center gap-2 text-center"
                in:fade={{ duration: 200 }}
            >
                <h1 class="text-4xl font-medium text-white">
                    hi <span
                        class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
                        style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
                        >simone</span
                    >
                </h1>
                <p class="text-xl text-white/60">good afternoon</p>
            </div>
            <ChatInputLiquidGlass
                bind:value={inputValue}
                onSubmit={handleSendMessage}
                onStop={handleStopGeneration}
                {isGenerating}
                placeholder="send a message"
            />
        </div>
    </div>
</div>
