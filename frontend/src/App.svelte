<script lang="ts">
    import AppSidebar from '$lib/components/sidebar/AppSidebar.svelte'
    import * as Tooltip from '$lib/components/ui/tooltip'
    import { createSidebarContext } from '$lib/contexts/sidebarContext.svelte'
    import GalaxyBackgroundWebGL from './lib/components/backgrounds/webgl/GalaxyBackgroundWebGL.svelte'
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

    function handleEditMessage(messageId: string) {
        console.log('Edit message:', messageId)
    }
</script>

<Tooltip.Provider>
    <!-- Galaxy background wraps everything to provide context -->
    <GalaxyBackgroundWebGL>
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
                            {#each messages as message, index (message.id)}
                                {#if message.role === 'user'}
                                    <UserChatMessage
                                        content={message.content}
                                        timestamp={message.timestamp}
                                    >
                                        {#snippet actions()}
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
                                                onclick={() => handleEditMessage(message.id)}
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
                                                        d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"
                                                    />
                                                    <path d="m15 5 4 4" />
                                                </svg>
                                            </Button>
                                        {/snippet}
                                    </UserChatMessage>
                                {:else}
                                    <AssistantChatMessage
                                        content={message.content}
                                        timestamp={message.timestamp}
                                        isLastMessage={index === messages.length - 1}
                                    >
                                        {#snippet actions()}
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
                                        {/snippet}
                                    </AssistantChatMessage>
                                {/if}
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
    </GalaxyBackgroundWebGL>
</Tooltip.Provider>
