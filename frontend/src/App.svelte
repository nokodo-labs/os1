<script lang="ts">
    import type { BackgroundType } from '$lib/components/backgrounds/BackgroundManager.svelte'
    import BackgroundManager from '$lib/components/backgrounds/BackgroundManager.svelte'
    import DebugMenu from '$lib/components/debug/DebugMenu.svelte'
    import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
    import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
    import Pencil from '$lib/components/icons/Pencil.svelte'
    import AppSidebar from '$lib/components/sidebar/AppSidebar.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import { createThemeContext } from '$lib/contexts/themeContext.svelte'
    import { fade } from 'svelte/transition'
    import AssistantChatMessage from './lib/components/chat/AssistantChatMessage.svelte'
    import Button from './lib/components/chat/Button.svelte'
    import ChatHeader from './lib/components/chat/ChatHeader.svelte'
    import ChatInputLiquidGlass from './lib/components/chat/ChatInput.svelte'
    import FloatingButtons from './lib/components/chat/FloatingButtons.svelte'
    import UserChatMessage from './lib/components/chat/UserChatMessage.svelte'
    import './lib/styles/liquid-glass.css'
    // Initialize sidebar context
    const sidebar = createSidebarContext()
    // Initialize theme context
    const theme = createThemeContext()

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

    function handleFloatingAdd(newMessages: { role: 'user' | 'assistant'; content: string }[]) {
        if (messages.length === 0) {
            sidebar.selectChat(Date.now().toString())
        }

        newMessages.forEach((msg) => {
            messages.push({
                id: Date.now().toString() + Math.random().toString(),
                role: msg.role,
                content: msg.content,
                timestamp: new Date(),
                model: msg.role === 'assistant' ? selectedModel : undefined,
            })
        })
    }
</script>

<Tooltip.Provider>
    <!-- Background Manager handles all backgrounds with smooth transitions -->
    <BackgroundManager type={currentBackground} config={{ color: '#0a0a0a' }}>
        <FloatingButtons onAdd={handleFloatingAdd} />
        <!-- DEV ONLY: Debug Menu -->
        <DebugMenu {theme} bind:currentBackground />

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
                                    <h1 class="text-4xl font-medium text-white">
                                        hi <span
                                            class="bg-clip-text text-transparent [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]"
                                            style="background-image: linear-gradient(to bottom right, var(--accent-secondary), var(--accent-primary));"
                                            >simone</span
                                        >
                                    </h1>
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
