<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
    import AppSidebar from '$lib/components/sidebar/AppSidebar.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import Button from './lib/components/chat/Button.svelte'
    import ChatHeader from './lib/components/chat/ChatHeader.svelte'
    import ChatInputLiquidGlass from './lib/components/chat/ChatInput.svelte'
    import ChatMessageWebGL from './lib/components/chat/webgl/ChatMessageWebGL.svelte'
    import './lib/styles/liquid-glass.css'
    // Initialize sidebar context
    const sidebar = createSidebarContext()

    interface Message {
        id: string
        role: 'user' | 'assistant'
        content: string
        timestamp: Date
    }

    interface Model {
        id: string
        name: string
        provider: string
    }

    // Demo data
    const models: Model[] = [
        { id: 'gpt-4', name: 'GPT-4', provider: 'OpenAI' },
        { id: 'claude-3', name: 'Claude 3 Opus', provider: 'Anthropic' },
        { id: 'gemini-pro', name: 'Gemini Pro', provider: 'Google' },
    ]

    let selectedModel = $state('gpt-4')
    let messages = $state<Message[]>([
        {
            id: '1',
            role: 'assistant',
            content:
                "Welcome to nokodo AI! 🚀 I'm here to help you build the next generation of AI experiences. What would you like to create today?",
            timestamp: new Date(),
        },
    ])

    let inputValue = $state('')

    // DEV ONLY: Background switcher
    let currentBackground = $state<BackgroundType>('darkveil')
    let showBgDropdown = $state(false)

    const backgrounds: { value: BackgroundType; label: string }[] = [
        { value: 'galaxy', label: 'Galaxy' },
        { value: 'darkveil', label: 'Dark Veil' },
        { value: 'lightbends', label: 'Light Bends' },
        { value: 'lightrays', label: 'Light Rays' },
        { value: 'silk', label: 'Silk' },
        { value: 'static', label: 'Static Color' },
        { value: 'none', label: 'None' },
    ]

    function handleSendMessage(content: string) {
        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content,
            timestamp: new Date(),
        }
        messages.push(userMessage)

        // Simulate AI response
        setTimeout(() => {
            const aiMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: `I received your message: "${content}". This is a demo response showcasing the liquid UI!`,
                timestamp: new Date(),
            }
            messages.push(aiMessage)
        }, 1000)
    }

    function handleModelSelect(modelId: string) {
        selectedModel = modelId
    }

    function handleCopyMessage(content: string) {
        navigator.clipboard.writeText(content)
    }

    function handleRegenerateMessage() {
        console.log('Regenerate message')
    }
</script>

<Tooltip.Provider>
    <!-- Background Manager handles all backgrounds with smooth transitions -->
    <BackgroundManager type={currentBackground} config={{ color: '#0a0a0a' }}>
        <!-- DEV ONLY: Background switcher dropdown -->
        <div class="fixed top-4 right-4 z-50">
            <div class="relative">
                <button
                    onclick={() => (showBgDropdown = !showBgDropdown)}
                    class="rounded-lg bg-black/50 px-3 py-2 text-xs text-white/80 backdrop-blur-sm transition-colors hover:bg-black/70 hover:text-white"
                >
                    BG: {backgrounds.find((b) => b.value === currentBackground)?.label}
                    <span class="ml-1">▼</span>
                </button>

                {#if showBgDropdown}
                    <div
                        class="absolute top-full right-0 mt-1 w-40 rounded-lg bg-black/90 p-1 shadow-xl backdrop-blur-sm"
                    >
                        {#each backgrounds as bg}
                            <button
                                onclick={() => {
                                    currentBackground = bg.value
                                    showBgDropdown = false
                                }}
                                class="block w-full rounded px-3 py-1.5 text-left text-xs text-white/80 transition-colors hover:bg-white/10 hover:text-white {currentBackground ===
                                bg.value
                                    ? 'bg-white/10 font-medium text-white'
                                    : ''}"
                            >
                                {bg.label}
                            </button>
                        {/each}
                    </div>
                {/if}
            </div>
        </div>

        <div class="relative z-1 flex h-screen">
            <!-- Sidebar -->
            <AppSidebar />

            <!-- Main Content -->
            <div class="flex min-w-0 flex-1 flex-col">
                <div class="flex min-h-0 flex-1 flex-col">
                    <div class="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col">
                        <ChatHeader
                            selectedAgent={selectedModel}
                            onAgentChange={(agentId: string) => (selectedModel = agentId)}
                        ></ChatHeader>

                        <div class="flex flex-1 flex-col gap-6 overflow-y-auto p-8">
                            {#each messages as message (message.id)}
                                <ChatMessageWebGL
                                    role={message.role}
                                    content={message.content}
                                    timestamp={message.timestamp}
                                >
                                    {#snippet actions()}
                                        {#if message.role === 'assistant'}
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onclick={() => handleCopyMessage(message.content)}
                                            >
                                                <svg
                                                    width="14"
                                                    height="14"
                                                    viewBox="0 0 24 24"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    stroke-width="2"
                                                    stroke-linecap="round"
                                                    stroke-linejoin="round"
                                                >
                                                    <rect
                                                        width="14"
                                                        height="14"
                                                        x="8"
                                                        y="8"
                                                        rx="2"
                                                        ry="2"
                                                    />
                                                    <path
                                                        d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"
                                                    />
                                                </svg>
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onclick={handleRegenerateMessage}
                                            >
                                                <svg
                                                    width="14"
                                                    height="14"
                                                    viewBox="0 0 24 24"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    stroke-width="2"
                                                    stroke-linecap="round"
                                                    stroke-linejoin="round"
                                                >
                                                    <path
                                                        d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"
                                                    />
                                                    <path d="M21 3v5h-5" />
                                                </svg>
                                            </Button>
                                        {/if}
                                    {/snippet}
                                </ChatMessageWebGL>
                            {/each}
                        </div>

                        <div class="px-8 py-6 pb-8">
                            <ChatInputLiquidGlass
                                bind:value={inputValue}
                                onSubmit={handleSendMessage}
                                placeholder="Ask me anything..."
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </BackgroundManager>
</Tooltip.Provider>
