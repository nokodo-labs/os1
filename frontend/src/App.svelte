<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
    import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
    import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
    import Pencil from '$lib/components/icons/Pencil.svelte'
    import AppSidebar from '$lib/components/sidebar/AppSidebar.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import { fade } from 'svelte/transition'
    import AssistantChatMessage from './lib/components/chat/AssistantChatMessage.svelte'
    import Button from './lib/components/chat/Button.svelte'
    import ChatHeader from './lib/components/chat/ChatHeader.svelte'
    import ChatInputLiquidGlass from './lib/components/chat/ChatInput.svelte'
    import UserChatMessage from './lib/components/chat/UserChatMessage.svelte'
    import './lib/styles/liquid-glass.css'
    // Initialize sidebar context
    const sidebar = createSidebarContext()

    interface Message {
        id: string
        role: 'user' | 'assistant'
        content: string
        timestamp: Date
        model?: string
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
    let messages = $state<Message[]>([])

    // Track if the user has started chatting to animate the input from center to bottom
    let hasStartedChatting = $derived(messages.some((m) => m.role === 'user'))

    $effect(() => {
        if (sidebar.selectedChatId === null) {
            messages = []
        }
    })

    let inputValue = $state('')
    let isGenerating = $state(false)
    let generationTimeout: number | null = null

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
        if (messages.length === 0) {
            sidebar.selectChat(Date.now().toString())
        }
        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content,
            timestamp: new Date(),
        }
        messages.push(userMessage)

        // Immediate AI placeholder
        const aiMessageId = (Date.now() + 1).toString()
        const aiMessage: Message = {
            id: aiMessageId,
            role: 'assistant',
            content: '', // Start empty
            timestamp: new Date(),
            model: selectedModel,
        }
        messages.push(aiMessage)
        isGenerating = true

        // Simulate AI response streaming
        generationTimeout = setTimeout(() => {
            const response = `I received your message: "${content}". This is a demo response showcasing the liquid UI!`
            // Update the last message (which is the AI placeholder)
            const lastMsg = messages[messages.length - 1]
            if (lastMsg && lastMsg.id === aiMessageId) {
                lastMsg.content = response
            }
            isGenerating = false
            generationTimeout = null
        }, 1000) as unknown as number
    }

    function handleStopGeneration() {
        if (generationTimeout) {
            clearTimeout(generationTimeout)
            generationTimeout = null
        }
        isGenerating = false
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

    function handleEditMessage(messageId: string) {
        console.log('Edit message:', messageId)
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
            <div class="relative flex min-w-0 flex-1 flex-col">
                <!-- Scrollable Area -->
                <div class="flex-1 overflow-y-auto">
                    <div class="mx-auto flex min-h-full w-full max-w-4xl flex-col px-8 pt-8 pb-32">
                        <ChatHeader
                            selectedAgent={selectedModel}
                            onAgentChange={(agentId: string) => (selectedModel = agentId)}
                        ></ChatHeader>

                        <div class="flex flex-1 flex-col gap-6 py-8">
                            {#each messages as message, index (message.id)}
                                <div transition:fade={{ duration: 200 }}>
                                    {#if message.role === 'user'}
                                        <UserChatMessage
                                            content={message.content}
                                            timestamp={message.timestamp}
                                        >
                                            {#snippet actions()}
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onclick={() =>
                                                        handleCopyMessage(message.content)}
                                                >
                                                    <DocumentDuplicate
                                                        className="w-3.5 h-3.5"
                                                        strokeWidth="2"
                                                    />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onclick={() => handleEditMessage(message.id)}
                                                >
                                                    <Pencil
                                                        className="w-3.5 h-3.5"
                                                        strokeWidth="2"
                                                    />
                                                </Button>
                                            {/snippet}
                                        </UserChatMessage>
                                    {:else}
                                        <AssistantChatMessage
                                            content={message.content}
                                            timestamp={message.timestamp}
                                            modelName={message.model}
                                            isLastMessage={index === messages.length - 1}
                                        >
                                            {#snippet actions()}
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onclick={() =>
                                                        handleCopyMessage(message.content)}
                                                >
                                                    <DocumentDuplicate
                                                        className="w-3.5 h-3.5"
                                                        strokeWidth="2"
                                                    />
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onclick={handleRegenerateMessage}
                                                >
                                                    <ArrowPath
                                                        className="w-3.5 h-3.5"
                                                        strokeWidth="2"
                                                    />
                                                </Button>
                                            {/snippet}
                                        </AssistantChatMessage>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    </div>
                </div>

                <!-- Input Area (Fixed Bottom) -->
                <div class="absolute right-0 bottom-0 left-0 z-10 pt-10 pb-8">
                    <div class="mx-auto w-full max-w-4xl px-8">
                        <div
                            class="transition-all duration-500 ease-in-out"
                            class:-translate-y-[40vh]={!hasStartedChatting}
                        >
                            {#if !hasStartedChatting}
                                <div
                                    class="mb-8 flex flex-col items-center justify-center gap-2 text-center"
                                    transition:fade={{ duration: 200 }}
                                >
                                    <h1 class="text-4xl font-medium text-white">hi simone</h1>
                                    <p class="text-xl text-white/60">good afternoon</p>
                                </div>
                            {/if}
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
            </div>
        </div>
    </BackgroundManager>
</Tooltip.Provider>
