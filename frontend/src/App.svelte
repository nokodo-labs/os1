<script lang="ts">
    import GalaxyBackgroundWebGL from './lib/components/backgrounds/webgl/GalaxyBackgroundWebGL.svelte'
    import Button from './lib/components/chat/Button.svelte'
    import ChatHeader from './lib/components/chat/ChatHeader.svelte'
    import ModelSelector from './lib/components/chat/ModelSelector.svelte'
    import ChatInputWebGL from './lib/components/chat/webgl/ChatInputWebGL.svelte'
    import ChatMessageWebGL from './lib/components/chat/webgl/ChatMessageWebGL.svelte'
    import liquidGlassFilter from './lib/styles/liquid-glass-filter.svg?raw'
    import './lib/styles/liquid-glass.css'

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
</script>

<svelte:head>{@html liquidGlassFilter}</svelte:head>

<!-- Galaxy background wraps everything to provide context -->
<GalaxyBackgroundWebGL>
    <div class="app-container">
        <ChatHeader title="nokodo AI" subtitle="Next-gen AI platform">
            {#snippet actions()}
                <ModelSelector {models} selected={selectedModel} onSelect={handleModelSelect} />
                <Button variant="ghost" size="sm">
                    <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    >
                        <path
                            d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
                        />
                        <circle cx="12" cy="12" r="3" />
                    </svg>
                </Button>
            {/snippet}
        </ChatHeader>

        <div class="messages-container">
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
                                    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                                    <path
                                        d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"
                                    />
                                </svg>
                            </Button>
                            <Button variant="ghost" size="sm" onclick={handleRegenerateMessage}>
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
                                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                                    <path d="M21 3v5h-5" />
                                </svg>
                            </Button>
                        {/if}
                    {/snippet}
                </ChatMessageWebGL>
            {/each}
        </div>

        <div class="input-container">
            <ChatInputWebGL
                bind:value={inputValue}
                onSubmit={handleSendMessage}
                placeholder="Ask me anything..."
            />
        </div>
    </div>
</GalaxyBackgroundWebGL>

<style>
    :global(body) {
        margin: 0;
        padding: 0;
        min-height: 100vh;
        background: #000;
        font-family:
            -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell,
            sans-serif;
    }

    .app-container {
        display: flex;
        flex-direction: column;
        height: 100vh;
        max-width: 1200px;
        margin: 0 auto;
        position: relative;
        z-index: 1;
    }

    .messages-container {
        flex: 1;
        overflow-y: auto;
        padding: 2rem;
        display: flex;
        flex-direction: column;
        gap: 1.5rem;
        scrollbar-width: thin;
        scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
    }

    .messages-container::-webkit-scrollbar {
        width: 6px;
    }

    .messages-container::-webkit-scrollbar-track {
        background: transparent;
    }

    .messages-container::-webkit-scrollbar-thumb {
        background: rgba(255, 255, 255, 0.2);
        border-radius: 3px;
    }

    .messages-container::-webkit-scrollbar-thumb:hover {
        background: rgba(255, 255, 255, 0.3);
    }

    .input-container {
        padding: 1.5rem 2rem 2rem;
    }
</style>
